"""계정 / 로그인 API (docs/DB_RULES.md 2-1 B1~B4).

토큰은 `Authorization: Bearer <토큰>` 헤더로 주고받는다.
"""
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError

from .config import get_settings
from .db import Conn
from .security import DUMMY_HASH, hash_password, hash_token, new_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# B3: 자동로그인 해제 6시간, 설정 30일
SESSION_SHORT = timedelta(hours=6)
SESSION_LONG = timedelta(days=30)


class SignupIn(BaseModel):
    아이디: str = Field(min_length=1, max_length=50, pattern=r"^\S+$")
    패스워드: str = Field(min_length=1, max_length=128)
    닉네임: str = Field(min_length=1, max_length=30)

    @field_validator("패스워드")
    @classmethod
    def long_enough(cls, value: str) -> str:
        """최소 글자 수는 설정(MM_PASSWORD_MIN_LENGTH, 기본 8)에서 읽는다. 화면이 항목별로 안내할 수 있게 같은 오류 종류를 쓴다."""
        minimum = get_settings().password_min_length
        if len(value) < minimum:
            raise PydanticCustomError("string_too_short", "String should have at least {min_length} characters", {"min_length": minimum})
        return value


class LoginIn(BaseModel):
    아이디: str = Field(max_length=50)
    패스워드: str = Field(max_length=128)
    접속환경: Literal["PC", "모바일"]
    자동로그인: bool = False


class AccountOut(BaseModel):
    번호: int
    아이디: str
    닉네임: str
    권한: Literal["사용자", "관리자", "운영자"]


class LoginOut(BaseModel):
    토큰: str
    만료일시: str
    계정: AccountOut


def _unauthorized(detail: str = "인증이 필요합니다") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def _bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized()
    return token


class CurrentSession(BaseModel):
    세션_번호: int
    계정: AccountOut


def current_session(conn: Conn, token: Annotated[str, Depends(_bearer_token)]) -> CurrentSession:
    """B1·B4: 폐기·만료된 세션과 상태가 `정상`이 아닌 계정은 거부한다."""
    row = conn.execute(
        """
        SELECT s."번호" AS 세션_번호, a."번호", a."아이디", a."닉네임", a."권한"
        FROM "로그인세션" s JOIN "계정" a ON a."번호" = s."계정_번호"
        WHERE s."토큰" = %s AND s."폐기일시" IS NULL
          AND s."만료일시" > CURRENT_TIMESTAMP AND a."상태" = '정상'
        """,
        (hash_token(token),),
    ).fetchone()
    if row is None:
        raise _unauthorized("세션이 없거나 만료되었습니다")
    return CurrentSession(
        세션_번호=row["세션_번호"],
        계정=AccountOut(번호=row["번호"], 아이디=row["아이디"], 닉네임=row["닉네임"], 권한=row["권한"]),
    )


CurrentUser = Annotated[CurrentSession, Depends(current_session, scope="function")]


@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=AccountOut)
def signup(body: SignupIn, conn: Conn) -> AccountOut:
    try:
        row = conn.execute(
            'INSERT INTO "계정" ("아이디", "패스워드", "닉네임") VALUES (%s, %s, %s) '
            'RETURNING "번호", "아이디", "닉네임", "권한"',
            (body.아이디, hash_password(body.패스워드), body.닉네임),
        ).fetchone()
    except UniqueViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 사용 중인 아이디입니다") from None
    return AccountOut(**row)


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, conn: Conn) -> LoginOut:
    acct = conn.execute(
        'SELECT "번호", "아이디", "패스워드", "닉네임", "권한", "상태" FROM "계정" WHERE "아이디" = %s',
        (body.아이디,),
    ).fetchone()
    # 아이디가 없어도 해시 검증을 수행하고, 아이디·비밀번호 오류는 같은 응답으로 돌려준다.
    ok = verify_password(body.패스워드, acct["패스워드"] if acct else DUMMY_HASH)
    if acct is None or not ok:
        raise _unauthorized("아이디 또는 패스워드가 올바르지 않습니다")
    if acct["상태"] != "정상":  # B1: 비밀번호가 맞은 경우에만 상태를 알려 준다.
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"로그인할 수 없는 계정입니다({acct['상태']})")

    token = new_token()
    ttl = SESSION_LONG if body.자동로그인 else SESSION_SHORT
    # 생성일시 기본값(CURRENT_TIMESTAMP)과 같은 트랜잭션 시각을 기준으로 만료일시를 계산한다.
    row = conn.execute(
        """
        INSERT INTO "로그인세션" ("계정_번호", "토큰", "만료일시", "접속환경")
        VALUES (%s, %s, CURRENT_TIMESTAMP + %s, %s) RETURNING "만료일시"
        """,
        (acct["번호"], hash_token(token), ttl, body.접속환경),
    ).fetchone()
    return LoginOut(
        토큰=token,
        만료일시=row["만료일시"].isoformat(),
        계정=AccountOut(번호=acct["번호"], 아이디=acct["아이디"], 닉네임=acct["닉네임"], 권한=acct["권한"]),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(conn: Conn, cur: CurrentUser) -> None:
    conn.execute(
        'UPDATE "로그인세션" SET "폐기일시" = CURRENT_TIMESTAMP WHERE "번호" = %s',
        (cur.세션_번호,),
    )


@router.get("/me", response_model=AccountOut)
def me(cur: CurrentUser) -> AccountOut:
    return cur.계정
