"""계정 / 로그인 API (docs/DB_RULES.md 2-1 B1~B4).

토큰은 `Authorization: Bearer <토큰>` 헤더로 주고받는다.
"""
import threading
import time
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError

from .config import get_settings
from .db import Conn
from .security import hash_password, hash_token, new_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# B3: 자동로그인 해제 6시간, 설정 30일
SESSION_SHORT = timedelta(hours=6)
SESSION_LONG = timedelta(days=30)


def check_password_length(value: str) -> str:
    """최소 글자 수는 설정(MM_PASSWORD_MIN_LENGTH, 기본 8)에서 읽는다. 화면이 항목별로 안내할 수 있게 같은 오류 종류를 쓴다."""
    minimum = get_settings().password_min_length
    if len(value) < minimum:
        raise PydanticCustomError("string_too_short", "String should have at least {min_length} characters", {"min_length": minimum})
    return value


class SignupIn(BaseModel):
    아이디: str = Field(min_length=1, max_length=50, pattern=r"^\S+$")
    패스워드: str = Field(min_length=1, max_length=128)
    닉네임: str = Field(min_length=1, max_length=30)

    @field_validator("패스워드")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return check_password_length(value)


class ResetIn(BaseModel):
    """패스워드 초기화: 아이디와 닉네임이 둘 다 맞아야 한다(사용자 결정 2026-10-18)."""

    아이디: str = Field(min_length=1, max_length=50)
    닉네임: str = Field(min_length=1, max_length=30)
    새_패스워드: str = Field(min_length=1, max_length=128)

    @field_validator("새_패스워드")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return check_password_length(value)


class LoginGuard:
    """같은 아이디로 패스워드를 연속으로 틀린 횟수를 세고, 한도에 이르면 일정 시간 막는다(아이디 기준, 서버 메모리).

    로그인과 패스워드 초기화의 실패를 함께 센다. 성공하면 0으로 돌아가고, 막는 시간이 끝나면 다시 처음부터 센다.
    서버는 프로세스 하나로만 실행하므로 메모리에 둔다(재시작하면 풀린다).
    """

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self._lock = threading.Lock()
        self._state: dict[str, list[float]] = {}          # 아이디 → [연속 실패 수, 막힌 시각(없으면 0)]

    def remaining(self, key: str) -> float:
        """막혀 있으면 풀릴 때까지 남은 초, 아니면 0."""
        with self._lock:
            state = self._state.get(key)
            if not state or not state[1]:
                return 0.0
            left = state[1] + get_settings().login_lock_seconds - self.clock()
            if left <= 0:
                del self._state[key]                       # 막는 시간이 끝나면 처음부터 다시 센다
                return 0.0
            return left

    def fail(self, key: str) -> tuple[int, bool]:
        """실패를 한 번 센다. (남은 시도 횟수, 이번에 막혔는지)"""
        limit = get_settings().login_fail_limit
        with self._lock:
            state = self._state.setdefault(key, [0, 0.0])
            state[0] += 1
            if state[0] >= limit:
                state[1] = self.clock()
                return 0, True
            return limit - int(state[0]), False

    def succeed(self, key: str) -> None:
        with self._lock:
            self._state.pop(key, None)


guard = LoginGuard()


def _locked_error(seconds: float) -> HTTPException:
    total = max(int(seconds + 0.999), 1)
    minutes, rest = divmod(total, 60)
    wait = f"{minutes}분 {rest}초" if minutes and rest else (f"{minutes}분" if minutes else f"{rest}초")
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"패스워드를 여러 번 틀려 잠시 막혔습니다. {wait} 뒤에 다시 시도해 주세요",
        headers={"Retry-After": str(total)},
    )


def _failed(key: str, detail: str) -> HTTPException:
    """실패를 세고, 이번에 막혔으면 막혔다고, 아니면 남은 횟수와 함께 알린다."""
    left, locked = guard.fail(key)
    if locked:
        return _locked_error(guard.remaining(key))
    return _unauthorized(f"{detail} (남은 시도 {left}회)")


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
    if acct is None:
        # 가입 화면이 이미 "이미 사용 중인 아이디"로 알려 주므로 숨기지 않는다(사용자 결정 2026-10-18).
        raise _unauthorized("아이디가 존재하지 않습니다")
    left = guard.remaining(body.아이디)
    if left:
        raise _locked_error(left)                          # 막혀 있는 동안은 맞는 패스워드도 받지 않는다
    if not verify_password(body.패스워드, acct["패스워드"]):
        raise _failed(body.아이디, "패스워드가 올바르지 않습니다")
    if acct["상태"] != "정상":  # B1: 비밀번호가 맞은 경우에만 상태를 알려 준다.
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"로그인할 수 없는 계정입니다({acct['상태']})")

    guard.succeed(body.아이디)
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


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(body: ResetIn, conn: Conn) -> None:
    """아이디와 닉네임이 둘 다 맞으면 새 패스워드를 정한다. 이메일 같은 확실한 본인 확인이 없어서 약한 확인이다(docs/BACKLOG.md).

    실패는 로그인 실패와 함께 세어 같은 제한을 받는다. 성공하면 그 계정의 로그인 세션을 모두 끊는다(주인이 로그인해 둔 상태면 쫓겨난다).
    """
    acct = conn.execute('SELECT "번호", "닉네임", "상태" FROM "계정" WHERE "아이디" = %s', (body.아이디,)).fetchone()
    if acct is None:
        raise _unauthorized("아이디가 존재하지 않습니다")
    left = guard.remaining(body.아이디)
    if left:
        raise _locked_error(left)
    if acct["닉네임"] != body.닉네임.strip():
        raise _failed(body.아이디, "닉네임이 맞지 않습니다")
    if acct["상태"] != "정상":
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"패스워드를 바꿀 수 없는 계정입니다({acct['상태']})")
    conn.execute('UPDATE "계정" SET "패스워드" = %s WHERE "번호" = %s', (hash_password(body.새_패스워드), acct["번호"]))
    conn.execute(
        'UPDATE "로그인세션" SET "폐기일시" = CURRENT_TIMESTAMP WHERE "계정_번호" = %s AND "폐기일시" IS NULL', (acct["번호"],)
    )
    guard.succeed(body.아이디)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(conn: Conn, cur: CurrentUser) -> None:
    conn.execute(
        'UPDATE "로그인세션" SET "폐기일시" = CURRENT_TIMESTAMP WHERE "번호" = %s',
        (cur.세션_번호,),
    )


@router.get("/me", response_model=AccountOut)
def me(cur: CurrentUser) -> AccountOut:
    return cur.계정
