"""작품 기본정보 API.

* 로그인한 계정의 작품만 다룬다. 남의 작품은 존재 여부를 알리지 않도록 404 로 응답한다.
* `최대인원` 은 직접 받지 않는다. NPC 가 아닌 인물 수로 자동 갱신된다 (인물이 0명이면 임시로 1).
* `상태`·`최신버전`·`공개여부` 는 확정·버전 기능(B6~B10)에서 다루므로 여기서 받지 않는다.
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from psycopg import Connection
from pydantic import BaseModel, Field

from .auth import CurrentUser
from .db import Conn

router = APIRouter(prefix="/api/works", tags=["works"])

WORK_COLUMNS = '"번호", "제목", "시놉시스", "장르", "최소인원", "최대인원", "예상시간", "상태", "생성일시", "수정일시"'


class WorkIn(BaseModel):
    제목: str = Field(min_length=1, max_length=100)
    시놉시스: str = Field(default="", max_length=5000)
    장르: str = Field(default="", max_length=50)
    예상시간: str = Field(default="3시간", min_length=1, max_length=50)


class WorkPatch(BaseModel):
    제목: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    시놉시스: Annotated[str, Field(max_length=5000)] | None = None
    장르: Annotated[str, Field(max_length=50)] | None = None
    예상시간: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    최소인원: Annotated[int, Field(ge=1, le=100)] | None = None


class WorkOut(BaseModel):
    번호: int
    제목: str
    시놉시스: str
    장르: str
    최소인원: int
    최대인원: int
    예상시간: str
    상태: str
    생성일시: datetime
    수정일시: datetime | None


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


@router.post("", status_code=status.HTTP_201_CREATED, response_model=WorkOut)
def create_work(body: WorkIn, conn: Conn, me: CurrentUser) -> dict:
    # 인물이 0명인 동안 최대인원은 임시로 1 이다. `최대 >= 최소` 제약 때문에 최소인원도 1 로 시작한다.
    return conn.execute(
        f'INSERT INTO "작품" ("제목", "시놉시스", "장르", "예상시간", "최소인원", "최대인원", "계정_번호") '
        f"VALUES (%s, %s, %s, %s, 1, 1, %s) RETURNING {WORK_COLUMNS}",
        (body.제목, body.시놉시스, body.장르, body.예상시간, me.계정.번호),
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
    changes = body.model_dump(exclude_unset=True)
    if None in changes.values():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "값을 비울 수 없는 항목입니다")
    if not changes:
        return work
    # DB 제약(최대 >= 최소)을 오류 대신 안내 메시지로 돌려준다. 최소인원은 인물 수(=최대인원)를 넘을 수 없다.
    if changes.get("최소인원", 1) > work["최대인원"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"최소인원은 현재 인원({work['최대인원']}명)보다 클 수 없습니다. 인물을 먼저 추가해 주세요",
        )
    assignments = ", ".join(f'"{col}" = %s' for col in changes)
    return conn.execute(
        f'UPDATE "작품" SET {assignments}, "수정일시" = CURRENT_TIMESTAMP WHERE "번호" = %s RETURNING {WORK_COLUMNS}',
        (*changes.values(), work_id),
    ).fetchone()
