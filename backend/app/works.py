"""작품 기본정보 API.

* 로그인한 계정의 작품만 다룬다. 남의 작품은 존재 여부를 알리지 않도록 404 로 응답한다.
* `최대인원`·`최소인원` 은 직접 받지 않는다. 인물에서 자동 계산된다(최대 = NPC 가 아닌 인물 수, 인물이 0명이면 임시로 1. 최소 = 최대 - NPC 가 될 수 있는 인물 수). 자세히는 characters.py.
* `상태`·`최신버전` 은 확정·버전 기능(B6~B8)에서 다루므로 여기서 받지 않는다.
* `공통스토리` 는 게임 시작 때 모두가 읽는 글이다. 비어 있을 수 있다 (개인 서사는 인물의 `서사`).
* `공개여부`·`공개권한` 은 여기서 바꾸지 않는다. 공개/비공개 전환은 `publishing.py` (B35)에서 한다.
"""
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from psycopg import Connection, errors
from pydantic import BaseModel, Field, model_validator

from . import narrative
from .auth import CurrentSession, CurrentUser
from .db import Conn
from .visibility import Level, actor_level

router = APIRouter(prefix="/api/works", tags=["works"])

WORK_COLUMNS = (
    '"번호", "제목", "시놉시스", "장르", "최소인원", "최대인원", "예상시간", "시간형식", "상태", "공개여부", "공개권한", "공통스토리", "생성일시", "수정일시", '
    'EXISTS (SELECT 1 FROM "버전" v WHERE v."작품_번호" = "작품"."번호") AS "확정버전_있음"'
)


TIME_FORMATS = ("시간만", "일까지", "월까지", "연도까지")
TimeFormat = Literal["시간만", "일까지", "월까지", "연도까지"]      # 타임라인 같은 시간을 어디까지 적을지(윗단위는 2000-01-01 로 채움)

UNTITLED = "제목없음"   # 임시 저장 이름. 제목을 비워서 만들면 이 이름으로 시작한다. 특별한 이름이 아니라 평범한 제목이며 같은 이름이 여럿이어도, 직접 "제목없음"으로 지어도 된다(제목은 언제든 고칠 수 있다)


class PartIn(BaseModel):
    """공통 스토리 한 부분. ID 는 이미 있는 부분을 다시 보낼 때만 넣고, 새 부분은 비운다(서버가 만든다)."""

    ID: str | None = Field(default=None, max_length=6)
    본문: str = Field(max_length=narrative.COMMON_TOTAL_LIMIT)


class PartOut(BaseModel):
    ID: str | None
    본문: str


def stored_common_story(raw: str | None, parts: list[PartIn] | None) -> str | None:
    """저장할 공통 스토리 글. 부분 목록(`공통스토리_부분`)이나 글(`공통스토리`) 중 하나로 받고, 둘 다 없으면 None(바꾸지 않음).

    글로 받으면 부분으로 나눠 다시 합친다(표기 검사, 글자 수 검사, 표기 없는 부분에 ID 붙이기). 개인 서사와 같은 규칙이다.
    """
    if parts is not None and raw:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "공통스토리와 공통스토리_부분 중 하나로만 보내 주세요")
    kwargs = {"total": narrative.COMMON_TOTAL_LIMIT, "noun": "공통 스토리"}
    try:
        if parts is not None:
            return narrative.join([narrative.Part(p.ID, p.본문) for p in parts], **kwargs)
        if raw is None:
            return None
        return narrative.join(narrative.split(raw), **kwargs)
    except narrative.NarrativeError as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from None


class WorkIn(BaseModel):
    제목: str = Field(default="", max_length=100)
    시놉시스: str = Field(default="", max_length=5000)
    장르: str = Field(default="", max_length=50)
    예상시간: str = Field(default="3시간", min_length=1, max_length=50)
    시간형식: TimeFormat = "시간만"
    공통스토리: str = Field(default="", max_length=narrative.COMMON_TOTAL_LIMIT + 400)
    공통스토리_부분: list[PartIn] | None = None


class WorkPatch(BaseModel):
    제목: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    시놉시스: Annotated[str, Field(max_length=5000)] | None = None
    장르: Annotated[str, Field(max_length=50)] | None = None
    예상시간: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    시간형식: TimeFormat | None = None
    공통스토리: Annotated[str, Field(max_length=narrative.COMMON_TOTAL_LIMIT + 400)] | None = None
    공통스토리_부분: list[PartIn] | None = None


class WorkOut(BaseModel):
    번호: int
    제목: str
    시놉시스: str
    장르: str
    최소인원: int
    최대인원: int
    예상시간: str
    시간형식: TimeFormat
    상태: str
    공개여부: bool
    공개권한: Literal["제작자", "관리자", "운영자"]
    공통스토리: str | None
    생성일시: datetime
    수정일시: datetime | None
    확정버전_있음: bool

    공통스토리_부분: list[PartOut] = []
    """공통 스토리를 나눈 부분들(ID, 본문). 화면은 부분 표기 줄을 보지 않는다."""

    @model_validator(mode="before")
    @classmethod
    def _split_story(cls, row: Any) -> Any:
        """DB 에는 부분 표기가 붙은 글로 저장되어 있다. 응답의 `공통스토리` 는 표기 없이 부분을 이은 글, 부분은 따로 담는다."""
        if not isinstance(row, dict) or "공통스토리" not in row:
            return row
        parts = narrative.split(row["공통스토리"] or "")
        return {**row, "공통스토리": "\n\n".join(p.text for p in parts) if row["공통스토리"] is not None else None,
                "공통스토리_부분": [{"ID": p.id, "본문": p.text} for p in parts]}


def not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "작품을 찾을 수 없습니다")


def lock_work(conn: Connection, work_id: int, account_id: int) -> dict:
    """내 작품을 잠그고 돌려준다. 같은 작품에 대한 쓰기 요청은 이 잠금으로 직렬화된다."""
    row = conn.execute(
        f'SELECT {WORK_COLUMNS} FROM "작품" WHERE "번호" = %s AND "계정_번호" = %s FOR UPDATE',
        (work_id, account_id),
    ).fetchone()
    if row is None:
        raise not_found()
    return row


def load_work_for_actor(
    conn: Connection, work_id: int, me: CurrentSession, *, lock: bool = False
) -> tuple[dict, Level, bool]:
    """작품과 요청자의 단계를 돌려준다. 소유자도 관리자·운영자도 아니면 존재를 숨기려고 404 를 낸다."""
    row = conn.execute(
        f'SELECT {WORK_COLUMNS}, "계정_번호" FROM "작품" WHERE "번호" = %s' + (" FOR UPDATE" if lock else ""),
        (work_id,),
    ).fetchone()
    if row is None:
        raise not_found()
    is_owner = row["계정_번호"] == me.계정.번호
    level = actor_level(me.계정.권한, is_owner)
    if level is None:
        raise not_found()
    return row, level, is_owner


@router.post("", status_code=status.HTTP_201_CREATED, response_model=WorkOut)
def create_work(body: WorkIn, conn: Conn, me: CurrentUser) -> dict:
    # 인물이 0명인 동안 최대인원은 임시로 1 이다. `최대 >= 최소` 제약 때문에 최소인원도 1 로 시작한다.
    return conn.execute(
        f'INSERT INTO "작품" ("제목", "시놉시스", "장르", "예상시간", "시간형식", "공통스토리", "최소인원", "최대인원", "계정_번호") '
        f"VALUES (%s, %s, %s, %s, %s, %s, 1, 1, %s) RETURNING {WORK_COLUMNS}",
        (body.제목.strip() or UNTITLED, body.시놉시스, body.장르, body.예상시간, body.시간형식,
         stored_common_story(body.공통스토리, body.공통스토리_부분) or "", me.계정.번호),
    ).fetchone()


@router.get("", response_model=list[WorkOut])
def list_works(conn: Conn, me: CurrentUser) -> list[dict]:
    return conn.execute(
        f'SELECT {WORK_COLUMNS} FROM "작품" WHERE "계정_번호" = %s ORDER BY "번호" DESC',
        (me.계정.번호,),
    ).fetchall()


@router.get("/{work_id}", response_model=WorkOut)
def get_work(work_id: int, conn: Conn, me: CurrentUser) -> dict:
    row = conn.execute(
        f'SELECT {WORK_COLUMNS} FROM "작품" WHERE "번호" = %s AND "계정_번호" = %s',
        (work_id, me.계정.번호),
    ).fetchone()
    if row is None:
        raise not_found()
    return row


@router.patch("/{work_id}", response_model=WorkOut)
def update_work(work_id: int, body: WorkPatch, conn: Conn, me: CurrentUser) -> dict:
    work = lock_work(conn, work_id, me.계정.번호)
    changes = body.model_dump(exclude_unset=True, exclude={"공통스토리_부분"})
    if body.공통스토리_부분 is not None or "공통스토리" in changes:
        story = stored_common_story(changes.get("공통스토리"), body.공통스토리_부분)
        if story is not None:
            changes["공통스토리"] = story
    if None in changes.values():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "값을 비울 수 없는 항목입니다")
    if not changes:
        return work
    assignments = ", ".join(f'"{col}" = %s' for col in changes)
    return conn.execute(
        f'UPDATE "작품" SET {assignments}, "수정일시" = CURRENT_TIMESTAMP WHERE "번호" = %s RETURNING {WORK_COLUMNS}',
        (*changes.values(), work_id),
    ).fetchone()


@router.delete("/{work_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_work(work_id: int, conn: Conn, me: CurrentUser, request: Request) -> None:
    """내 작품을 지운다. 제작용 콘텐츠·확정 버전·테스터는 물론 이 작품으로 만든 방과 플레이 기록도 함께 지워진다(되돌릴 수 없다).

    시험 삼아 플레이해 본 작품도 지울 수 있어야 해서(사용자 결정 2026-10-18) 방·진행·참여 기록을 먼저 지운 뒤 작품을 지운다.
    열려 있는 방(대기·진행 중)이 있으면 그 방도 닫힌다. DB 의 외래키는 여전히 직접 지우는 것을 막는다(docs/DB_RULES.md B11).
    """
    lock_work(conn, work_id, me.계정.번호)
    room_ids = [r["번호"] for r in conn.execute('SELECT "번호" FROM "방" WHERE "작품_번호" = %s', (work_id,)).fetchall()]
    try:
        conn.execute('DELETE FROM "진행" WHERE "작품_번호" = %s', (work_id,))     # 참여·획득·공개·기믹실행·엔딩·투표결과가 함께 지워진다
        conn.execute('DELETE FROM "방" WHERE "작품_번호" = %s', (work_id,))
        conn.execute('DELETE FROM "작품" WHERE "번호" = %s', (work_id,))
    except errors.ForeignKeyViolation as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "이 작품을 쓰는 기록이 남아 있어 삭제할 수 없습니다") from exc
    for room_id in room_ids:                                                      # 열려 있던 방은 서버 메모리에서도 닫는다
        request.app.state.rooms.remove_room(room_id)
        request.app.state.games.remove(room_id)
