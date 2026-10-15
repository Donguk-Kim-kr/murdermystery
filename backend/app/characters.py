"""인물 API (작품 안의 인물). 인물은 `순서`(작품별 1부터)로 가리킨다.

* 삭제할 수 있다. 다른 항목(단서·증언·후일담 등)이 가리키는 인물은 지울 수 없다. 새 번호는 현재 마지막 번호 + 1 이다 (B13: 중간 결번은 채우지 않는다).
* 인물을 만들거나 NPC 여부를 바꾸면 작품.최대인원을 `max(NPC 가 아닌 인물 수, 1)` 로 다시 계산한다 (B5).
"""
from fastapi import APIRouter, HTTPException, status
from psycopg import Connection, errors
from pydantic import BaseModel, Field

from .auth import CurrentUser
from .db import Conn
from .ordering import next_order
from .works import lock_work, not_found

router = APIRouter(prefix="/api/works/{work_id}/characters", tags=["characters"])

COLUMNS = '"순서", "이름", "직업", "나이", "성별", "서사", "타임라인", "능력", "비밀", "목표", "범인", "NPC"'


class CharacterIn(BaseModel):
    이름: str = Field(min_length=1, max_length=50)
    직업: str | None = Field(default=None, max_length=50)
    나이: int | None = Field(default=None, ge=0, le=200)
    성별: str | None = Field(default=None, max_length=20)
    서사: str = Field(default="", max_length=5000)
    타임라인: str | None = Field(default=None, max_length=5000)
    능력: str | None = Field(default=None, max_length=2000)
    비밀: str | None = Field(default=None, max_length=2000)
    목표: str | None = Field(default=None, max_length=2000)
    범인: bool = False
    NPC: bool = False


class CharacterPatch(BaseModel):
    이름: str | None = Field(default=None, min_length=1, max_length=50)
    직업: str | None = Field(default=None, max_length=50)
    나이: int | None = Field(default=None, ge=0, le=200)
    성별: str | None = Field(default=None, max_length=20)
    서사: str | None = Field(default=None, max_length=5000)
    타임라인: str | None = Field(default=None, max_length=5000)
    능력: str | None = Field(default=None, max_length=2000)
    비밀: str | None = Field(default=None, max_length=2000)
    목표: str | None = Field(default=None, max_length=2000)
    범인: bool | None = None
    NPC: bool | None = None


class CharacterOut(CharacterIn):
    순서: int
    서사: str


# 비울 수 없는(NOT NULL) 컬럼. 나머지는 null 로 지울 수 있다.
REQUIRED = {"이름", "서사", "범인", "NPC"}


def sync_capacity(conn: Connection, work_id: int, min_players: int) -> None:
    """작품.최대인원 = NPC 가 아닌 인물 수 (0명이면 임시로 1) 로 맞춘다 (B5)."""
    n = conn.execute(
        'SELECT count(*) AS n FROM "인물" WHERE "작품_번호" = %s AND NOT "NPC"', (work_id,)
    ).fetchone()["n"]
    capacity = max(n, 1)
    if capacity < min_players:
        # 최대 >= 최소 제약을 어기게 되는 변경은 거부한다 (트랜잭션 롤백으로 인물 변경도 취소된다).
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"플레이 가능한 인물이 최소인원({min_players}명)보다 적어집니다. 최소인원을 먼저 낮춰 주세요",
        )
    conn.execute(
        'UPDATE "작품" SET "최대인원" = %s, "수정일시" = CURRENT_TIMESTAMP WHERE "번호" = %s',
        (capacity, work_id),
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CharacterOut)
def create_character(work_id: int, body: CharacterIn, conn: Conn, me: CurrentUser) -> dict:
    work = lock_work(conn, work_id, me.계정.번호)
    values = body.model_dump()
    order = next_order(conn, "인물", work_id)
    cols = list(values)
    row = conn.execute(
        'INSERT INTO "인물" ("작품_번호", "순서", ' + ", ".join(f'"{c}"' for c in cols) + ") "
        "VALUES (%s, %s, " + ", ".join(["%s"] * len(cols)) + f") RETURNING {COLUMNS}",
        (work_id, order, *values.values()),
    ).fetchone()
    sync_capacity(conn, work_id, work["최소인원"])
    return row


@router.get("", response_model=list[CharacterOut])
def list_characters(work_id: int, conn: Conn, me: CurrentUser) -> list[dict]:
    _ensure_mine(conn, work_id, me.계정.번호)
    return conn.execute(
        f'SELECT {COLUMNS} FROM "인물" WHERE "작품_번호" = %s ORDER BY "순서"', (work_id,)
    ).fetchall()


@router.get("/{order}", response_model=CharacterOut)
def get_character(work_id: int, order: int, conn: Conn, me: CurrentUser) -> dict:
    _ensure_mine(conn, work_id, me.계정.번호)
    return _get(conn, work_id, order)


@router.patch("/{order}", response_model=CharacterOut)
def update_character(work_id: int, order: int, body: CharacterPatch, conn: Conn, me: CurrentUser) -> dict:
    work = lock_work(conn, work_id, me.계정.번호)
    changes = body.model_dump(exclude_unset=True)
    if any(changes.get(col, 0) is None for col in REQUIRED):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "값을 비울 수 없는 항목입니다")
    current = _get(conn, work_id, order)
    if not changes:
        return current
    assignments = ", ".join(f'"{col}" = %s' for col in changes)
    row = conn.execute(
        f'UPDATE "인물" SET {assignments} WHERE "작품_번호" = %s AND "순서" = %s RETURNING {COLUMNS}',
        (*changes.values(), work_id, order),
    ).fetchone()
    if "NPC" in changes and changes["NPC"] != current["NPC"]:
        sync_capacity(conn, work_id, work["최소인원"])
    return row


def _ensure_mine(conn: Connection, work_id: int, account_id: int) -> None:
    if conn.execute(
        'SELECT 1 FROM "작품" WHERE "번호" = %s AND "계정_번호" = %s', (work_id, account_id)
    ).fetchone() is None:
        raise not_found()


def _get(conn: Connection, work_id: int, order: int) -> dict:
    row = conn.execute(
        f'SELECT {COLUMNS} FROM "인물" WHERE "작품_번호" = %s AND "순서" = %s', (work_id, order)
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "인물을 찾을 수 없습니다")
    return row


@router.delete("/{order}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(work_id: int, order: int, conn: Conn, me: CurrentUser) -> None:
    work = lock_work(conn, work_id, me.계정.번호)
    _get(conn, work_id, order)
    try:
        conn.execute('DELETE FROM "인물" WHERE "작품_번호" = %s AND "순서" = %s', (work_id, order))
    except errors.ForeignKeyViolation:
        # 단서·증언·후일담 등이 이 인물을 가리키고 있으면 지울 수 없다 (조용히 연결을 끊으면 의미가 바뀐다)
        raise HTTPException(
            status.HTTP_409_CONFLICT, "다른 항목이 이 인물을 사용하고 있어 지울 수 없습니다. 먼저 연결을 끊어 주세요"
        ) from None
    sync_capacity(conn, work_id, work["최소인원"])
