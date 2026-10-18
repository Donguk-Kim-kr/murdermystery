"""페이즈(진행순서) 끼워 넣기·옮기기·지우기, 칸에 놓인 카드의 표시 이름.

진행순서의 `순서`는 다른 테이블(진행구성, 기믹적용, 투표, 미디어)이 복합 외래키로 가리키는 칸 번호라서 바꿀 수 없다.
그래서 페이즈를 끼워 넣거나 옮길 때 칸은 그대로 두고 **칸에 매달린 내용**(그 칸을 가리키는 행들과 진행시간·이름)을 옮긴다.
한 요청은 한 트랜잭션이고 작품 잠금 아래에서 실행되므로 중간 상태는 밖에서 보이지 않는다.

"몇 번째 페이즈"는 칸 번호가 아니라 **칸 번호 순서로 센 위치**(1부터)이다. 지우기로 칸 번호에 빈틈이 생겨도 위치로 다룬다.
"""
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from psycopg import Connection, errors
from pydantic import BaseModel, Field

from .auth import CurrentUser
from .content import touch_work
from .db import Conn
from .ordering import next_order
from .works import lock_work
from .josa import attach

router = APIRouter(prefix="/api/works/{work_id}/phases", tags=["phases"])

# 페이즈 칸을 가리키는 테이블. 식별자는 이 목록에서만 SQL 로 들어간다.
CHILD_TABLES = ("진행구성", "기믹적용", "투표", "미디어")
# 칸을 지울 때 함께 사라지는(카드를 내려놓는) 테이블 / 남아 있으면 지울 수 없는 테이블
DROPPED_WITH_SLOT = ("진행구성",)
BLOCKING = {"기믹적용": "기믹", "투표": "투표", "미디어": "미디어"}


class InsertBody(BaseModel):
    position: Annotated[int, Field(ge=1)]
    이름: Annotated[str | None, Field(max_length=100)] = None
    진행시간: Annotated[int, Field(ge=0, le=1440)] = 30


class MoveBody(BaseModel):
    position: Annotated[int, Field(ge=1)]


def _slots(conn: Connection, work_id: int) -> list[int]:
    return [r["순서"] for r in conn.execute(
        'SELECT "순서" FROM "진행순서" WHERE "작품_번호" = %s ORDER BY "순서"', (work_id,)
    ).fetchall()]


def _rows(conn: Connection, work_id: int) -> list[dict]:
    return conn.execute(
        'SELECT "순서", "이름", "진행시간" FROM "진행순서" WHERE "작품_번호" = %s ORDER BY "순서"', (work_id,)
    ).fetchall()


def _create_slot(conn: Connection, work_id: int, name: str | None = None, minutes: int = 30) -> int:
    order = next_order(conn, "진행순서", work_id)
    conn.execute(
        'INSERT INTO "진행순서" ("작품_번호", "순서", "이름", "진행시간") VALUES (%s, %s, %s, %s)',
        (work_id, order, name, minutes),
    )
    return order


def _move_content(conn: Connection, work_id: int, src: int, dst: int) -> None:
    """src 칸에 매달린 내용을 비어 있는 dst 칸으로 옮기고 src 는 빈 칸(이름 없음, 30분)으로 돌린다."""
    for table in CHILD_TABLES:
        conn.execute(
            f'UPDATE "{table}" SET "진행순서_순서" = %s WHERE "작품_번호" = %s AND "진행순서_순서" = %s',
            (dst, work_id, src),
        )
    conn.execute(
        'UPDATE "진행순서" AS d SET "이름" = s."이름", "진행시간" = s."진행시간" FROM "진행순서" AS s '
        'WHERE d."작품_번호" = %(w)s AND d."순서" = %(dst)s AND s."작품_번호" = %(w)s AND s."순서" = %(src)s',
        {"w": work_id, "src": src, "dst": dst},
    )
    conn.execute(
        'UPDATE "진행순서" SET "이름" = NULL, "진행시간" = 30 WHERE "작품_번호" = %s AND "순서" = %s', (work_id, src)
    )


def _result(conn: Connection, work_id: int) -> dict:
    return {"phases": _rows(conn, work_id)}


@router.post("/insert", status_code=status.HTTP_201_CREATED)
def insert_phase(work_id: int, body: InsertBody, conn: Conn, me: CurrentUser) -> dict:
    """position 번째 위치에 빈 페이즈를 끼워 넣는다. 그 위치 이후의 페이즈는 한 칸씩 뒤로 밀린다."""
    lock_work(conn, work_id, me.계정.번호)
    slots = _slots(conn, work_id)
    if body.position > len(slots) + 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "위치가 페이즈 수보다 클 수 없습니다")
    k = body.position - 1
    slots.append(_create_slot(conn, work_id))
    for i in range(len(slots) - 2, k - 1, -1):    # 뒤에서부터 비어 있는 다음 칸으로 한 칸씩 민다
        _move_content(conn, work_id, slots[i], slots[i + 1])
    conn.execute(
        'UPDATE "진행순서" SET "이름" = %s, "진행시간" = %s WHERE "작품_번호" = %s AND "순서" = %s',
        (body.이름 or None, body.진행시간, work_id, slots[k]),
    )
    touch_work(conn, work_id)
    return _result(conn, work_id)


@router.post("/{order}/move")
def move_phase(work_id: int, order: int, body: MoveBody, conn: Conn, me: CurrentUser) -> dict:
    """칸 번호가 order 인 페이즈를 position 번째 위치로 옮긴다. 사이에 있던 페이즈들은 한 칸씩 물러난다."""
    lock_work(conn, work_id, me.계정.번호)
    slots = _slots(conn, work_id)
    if order not in slots:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "페이즈를 찾을 수 없습니다")
    if body.position > len(slots):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "위치가 페이즈 수보다 클 수 없습니다")
    a, b = slots.index(order), body.position - 1
    if a != b:
        scratch = _create_slot(conn, work_id)          # 옮기는 동안 내용을 잠시 맡아 둘 임시 칸
        _move_content(conn, work_id, slots[a], scratch)
        step = 1 if a < b else -1
        for i in range(a + step, b + step, step):
            _move_content(conn, work_id, slots[i], slots[i - step])
        _move_content(conn, work_id, scratch, slots[b])
        conn.execute('DELETE FROM "진행순서" WHERE "작품_번호" = %s AND "순서" = %s', (work_id, scratch))
        touch_work(conn, work_id)
    return _result(conn, work_id)


@router.delete("/{order}")
def delete_phase(work_id: int, order: int, conn: Conn, me: CurrentUser) -> dict:
    """페이즈를 지운다. 놓인 카드는 함께 내려가고, 뒤의 페이즈들은 한 칸씩 앞으로 당겨진다.

    기믹·투표·미디어가 이 페이즈에 붙어 있으면 지울 수 없다(먼저 옮기거나 지워야 한다).
    """
    lock_work(conn, work_id, me.계정.번호)
    slots = _slots(conn, work_id)
    if order not in slots:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "페이즈를 찾을 수 없습니다")
    for table, label in BLOCKING.items():
        n = conn.execute(
            f'SELECT count(*) AS n FROM "{table}" WHERE "작품_번호" = %s AND "진행순서_순서" = %s', (work_id, order)
        ).fetchone()["n"]
        if n:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"이 페이즈에 {attach(label, '이/가')} {n}개 붙어 있어 지울 수 없습니다. 먼저 옮기거나 지워 주세요"
            )
    for table in DROPPED_WITH_SLOT:
        conn.execute(f'DELETE FROM "{table}" WHERE "작품_번호" = %s AND "진행순서_순서" = %s', (work_id, order))
    k = slots.index(order)
    try:
        for i in range(k + 1, len(slots)):
            _move_content(conn, work_id, slots[i], slots[i - 1])
        conn.execute('DELETE FROM "진행순서" WHERE "작품_번호" = %s AND "순서" = %s', (work_id, slots[-1]))
    except errors.Error as exc:     # 위에서 막았으므로 도달하지 않아야 한다
        raise HTTPException(status.HTTP_409_CONFLICT, "다른 항목이 이 페이즈를 사용하고 있어 지울 수 없습니다") from exc
    touch_work(conn, work_id)
    return _result(conn, work_id)
