"""인물 API (작품 안의 인물). 인물은 `순서`(작품별 1부터)로 가리킨다.

* 삭제할 수 있다. 다른 항목(단서·증언·후일담 등)이 가리키는 인물은 지울 수 없다. 새 번호는 현재 마지막 번호 + 1 이다 (B13: 중간 결번은 채우지 않는다).
* 인물을 만들거나 NPC 여부·NPC 순위를 바꾸면 작품.최대인원과 최소인원을 다시 계산한다 (B5, 사용자 2026-10-18).
  최대인원 = `max(NPC 가 아닌 인물 수, 1)`, 최소인원 = `max(최대인원 - NPC 가 될 수 있는 인물 수, 1)`. 제작자가 직접 정하지 않는다.
* 인물은 세 종류이다. 항상 NPC(`NPC`, 예: 시작부터 죽은 피해자), NPC 가 될 수 있는 인물(`NPC순위` 가 있음, 1 이 가장 먼저 NPC 가 된다),
  반드시 플레이하는 인물(둘 다 아님). 순위는 작품 안에서 겹치지 않고, 항상 NPC 인 인물에는 둘 수 없다.
"""
from fastapi import APIRouter, HTTPException, status
from psycopg import Connection, errors
from pydantic import BaseModel, Field

from . import narrative
from .auth import CurrentUser
from .db import Conn
from .ordering import next_order
from .works import lock_work, not_found

router = APIRouter(prefix="/api/works/{work_id}/characters", tags=["characters"])

COLUMNS = '"순서", "이름", "직업", "나이", "성별", "서사", "타임라인", "능력", "비밀", "목표", "범인", "NPC", "소개", "캐릭터설명", "NPC순위"'


class PartIn(BaseModel):
    """서사 한 부분. ID 는 이미 있는 부분을 다시 보낼 때만 넣고, 새 부분은 비운다(서버가 만든다)."""

    ID: str | None = Field(default=None, max_length=6)
    본문: str = Field(max_length=narrative.TOTAL_LIMIT)


class PartOut(BaseModel):
    ID: str | None
    본문: str


class CharacterIn(BaseModel):
    이름: str = Field(min_length=1, max_length=50)
    직업: str | None = Field(default=None, max_length=50)
    나이: int | None = Field(default=None, ge=0, le=200)
    성별: str | None = Field(default=None, max_length=20)
    서사: str = Field(default="", max_length=narrative.TOTAL_LIMIT + 400)
    서사_부분: list[PartIn] | None = None
    타임라인: str | None = Field(default=None, max_length=5000)
    능력: str | None = Field(default=None, max_length=2000)
    비밀: str | None = Field(default=None, max_length=2000)
    목표: str | None = Field(default=None, max_length=2000)
    범인: bool = False
    NPC: bool = False
    소개: str | None = Field(default=None, max_length=1000)           # 자기소개 단계의 멘트
    캐릭터설명: str | None = Field(default=None, max_length=1000)       # 캐릭터 선택 화면과 캐릭터 설명 탭에 보여 줄 수 있는 설명
    NPC순위: int | None = Field(default=None, ge=1, le=100)


class CharacterPatch(BaseModel):
    이름: str | None = Field(default=None, min_length=1, max_length=50)
    직업: str | None = Field(default=None, max_length=50)
    나이: int | None = Field(default=None, ge=0, le=200)
    성별: str | None = Field(default=None, max_length=20)
    서사: str | None = Field(default=None, max_length=narrative.TOTAL_LIMIT + 400)
    서사_부분: list[PartIn] | None = None
    타임라인: str | None = Field(default=None, max_length=5000)
    능력: str | None = Field(default=None, max_length=2000)
    비밀: str | None = Field(default=None, max_length=2000)
    목표: str | None = Field(default=None, max_length=2000)
    범인: bool | None = None
    NPC: bool | None = None
    소개: str | None = Field(default=None, max_length=1000)
    캐릭터설명: str | None = Field(default=None, max_length=1000)
    NPC순위: int | None = Field(default=None, ge=1, le=100)


class CharacterOut(CharacterIn):
    순서: int
    서사: str
    서사_부분: list[PartOut] = []


# 비울 수 없는(NOT NULL) 컬럼. 나머지는 null 로 지울 수 있다.
REQUIRED = {"이름", "서사", "범인", "NPC"}


def sync_capacity(conn: Connection, work_id: int) -> None:
    """작품.최대인원과 최소인원을 인물에서 다시 계산한다 (B5).

    최대 = NPC 가 아닌 인물 수(0명이면 임시로 1), 최소 = 최대 - NPC 가 될 수 있는 인물 수(1 아래로는 내려가지 않는다).
    """
    row = conn.execute(
        'SELECT count(*) FILTER (WHERE NOT "NPC") AS n, count("NPC순위") AS ranked FROM "인물" WHERE "작품_번호" = %s', (work_id,)
    ).fetchone()
    capacity = max(row["n"], 1)
    minimum = max(capacity - row["ranked"], 1)
    conn.execute(
        'UPDATE "작품" SET "최대인원" = %s, "최소인원" = %s, "수정일시" = CURRENT_TIMESTAMP WHERE "번호" = %s',
        (capacity, minimum, work_id),
    )


def stored_story(raw: str | None, parts: list[PartIn] | None) -> str | None:
    """저장할 서사 글. 부분 목록(`서사_부분`)이나 글(`서사`) 중 하나로 받고, 둘 다 없으면 None(바꾸지 않음).

    글로 받으면 부분으로 나눠 다시 합친다(표기 검사, 글자 수 검사, 표기 없는 부분에 ID 붙이기). 둘 다 주면 거부한다.
    """
    if parts is not None and raw:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "서사와 서사_부분 중 하나로만 보내 주세요")
    try:
        if parts is not None:
            return narrative.join([narrative.Part(p.ID, p.본문) for p in parts])
        if raw is None:
            return None
        return narrative.join(narrative.split(raw))
    except narrative.NarrativeError as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from None


def present(row: dict) -> dict:
    """응답에 서사의 부분 목록(ID, 본문)을 덧붙인다. 화면은 표기 줄을 보지 않는다."""
    return {**row, "서사_부분": [{"ID": p.id, "본문": p.text} for p in narrative.split(row["서사"])]}


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CharacterOut)
def create_character(work_id: int, body: CharacterIn, conn: Conn, me: CurrentUser) -> dict:
    lock_work(conn, work_id, me.계정.번호)
    values = body.model_dump(exclude={"서사_부분"})
    values["서사"] = stored_story(body.서사, body.서사_부분)
    check_rank(values.get("NPC"), values.get("NPC순위"))
    order = next_order(conn, "인물", work_id)
    cols = list(values)
    try:
        row = conn.execute(
            'INSERT INTO "인물" ("작품_번호", "순서", ' + ", ".join(f'"{c}"' for c in cols) + ") "
            "VALUES (%s, %s, " + ", ".join(["%s"] * len(cols)) + f") RETURNING {COLUMNS}",
            (work_id, order, *values.values()),
        ).fetchone()
    except errors.UniqueViolation:
        raise rank_taken(values.get("NPC순위")) from None
    sync_capacity(conn, work_id)
    return present(row)


@router.get("", response_model=list[CharacterOut])
def list_characters(work_id: int, conn: Conn, me: CurrentUser) -> list[dict]:
    _ensure_mine(conn, work_id, me.계정.번호)
    rows = conn.execute(
        f'SELECT {COLUMNS} FROM "인물" WHERE "작품_번호" = %s ORDER BY "순서"', (work_id,)
    ).fetchall()
    return [present(r) for r in rows]


@router.get("/{order}", response_model=CharacterOut)
def get_character(work_id: int, order: int, conn: Conn, me: CurrentUser) -> dict:
    _ensure_mine(conn, work_id, me.계정.번호)
    return present(_get(conn, work_id, order))


@router.patch("/{order}", response_model=CharacterOut)
def update_character(work_id: int, order: int, body: CharacterPatch, conn: Conn, me: CurrentUser) -> dict:
    lock_work(conn, work_id, me.계정.번호)
    changes = body.model_dump(exclude_unset=True, exclude={"서사_부분"})
    if any(changes.get(col, 0) is None for col in REQUIRED):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "값을 비울 수 없는 항목입니다")
    story = stored_story(changes.get("서사"), body.서사_부분)
    if story is not None:
        changes["서사"] = story
    current = _get(conn, work_id, order)
    if changes.get("NPC") is True and "NPC순위" not in changes:
        changes["NPC순위"] = None              # 항상 NPC 로 바꾸면 NPC 가 될 수 있다는 표시는 필요 없다
    if not changes:
        return present(current)
    check_rank(changes.get("NPC", current["NPC"]), changes.get("NPC순위", current["NPC순위"]))
    assignments = ", ".join(f'"{col}" = %s' for col in changes)
    try:
        row = conn.execute(
            f'UPDATE "인물" SET {assignments} WHERE "작품_번호" = %s AND "순서" = %s RETURNING {COLUMNS}',
            (*changes.values(), work_id, order),
        ).fetchone()
    except errors.UniqueViolation:
        raise rank_taken(changes.get("NPC순위")) from None
    if "NPC" in changes or "NPC순위" in changes:
        sync_capacity(conn, work_id)
    return present(row)


def check_rank(npc: bool | None, rank: int | None) -> None:
    if npc and rank is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "항상 NPC 인 인물에는 NPC 순위를 둘 수 없습니다(NPC 가 될 수 있는 인물에만 둡니다)")


def rank_taken(rank: int | None) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, f"NPC 순위 {rank}은(는) 다른 인물이 이미 쓰고 있습니다. 순위는 인물마다 달라야 합니다")


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
    sync_capacity(conn, work_id)
