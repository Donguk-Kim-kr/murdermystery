"""테스터: 비공개 작품의 방 생성 권한 위임 (docs/DB_RULES.md B36).

* 제작자가 공개하지 않은 작품으로 지인끼리 플레이하거나 테스트할 수 있도록, 방을 만들 수 있는 권한을 계정에 준다.
  방 입장은 입장코드를 아는 사람이면 되므로 입장 권한이 아니다.
* 테스터 권한은 서버 전체 권한이 아니라 작품 단위로 계정에 주는 권한이다.
* 줄 수 있는 사람: 운영자·관리자(모든 작품), 제작자(자기 작품만). 회수도 같다.
* 방을 만들 수 있는 때(비공개 작품): 작품이 **비공개**이고 **공개권한이 제작자**일 때
  (= 최초 공개 전이거나 제작자가 비공개한 경우). 관리자·운영자가 비공개한 작품은 제외한다.
  공개된 작품은 누구나 플레이할 수 있으므로 테스터 권한과 무관하다.
* 방 기능이 생기면 `can_test_play()` 로 방 생성 가능 여부를 판단한다 (게임은 확정 버전이 있어야 시작된다).
"""
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from psycopg import Connection
from pydantic import BaseModel, Field

from .auth import CurrentUser
from .db import Conn
from .works import load_work_for_actor

router = APIRouter(tags=["testers"])

# 테스트 플레이 가능 조건 (작품 별칭 w, 테스터 부여 행 별칭 t). 제작자 본인은 테스터 행 없이도 해당한다.
_TESTABLE = 'NOT w."공개여부" AND w."공개권한" = \'제작자\' AND (w."계정_번호" = %(me)s OR t."계정_번호" IS NOT NULL)'
_FROM = 'FROM "작품" w LEFT JOIN "테스터" t ON t."작품_번호" = w."번호" AND t."계정_번호" = %(me)s'


class TesterIn(BaseModel):
    아이디: str = Field(min_length=1, max_length=50)


class TesterOut(BaseModel):
    계정_번호: int
    아이디: str
    닉네임: str
    부여일시: datetime


class TestableWorkOut(BaseModel):
    """테스터에게 보여 주는 작품 요약. 인물·단서 같은 내용(범인·비밀 포함)은 포함하지 않는다."""

    번호: int
    제목: str
    시놉시스: str
    장르: str
    최소인원: int
    최대인원: int
    예상시간: str


def can_test_play(conn: Connection, account_id: int, work_id: int) -> bool:
    return conn.execute(
        f'SELECT 1 {_FROM} WHERE w."번호" = %(work)s AND {_TESTABLE}', {"me": account_id, "work": work_id}
    ).fetchone() is not None


@router.get("/api/test-works", response_model=list[TestableWorkOut])
def my_test_works(conn: Conn, me: CurrentUser) -> list[dict]:
    """내가 지금 방을 만들 수 있는 비공개 작품 (내가 제작자인 작품 포함)."""
    return conn.execute(
        f'SELECT w."번호", w."제목", w."시놉시스", w."장르", w."최소인원", w."최대인원", w."예상시간" '
        f'{_FROM} WHERE {_TESTABLE} ORDER BY w."번호" DESC',
        {"me": me.계정.번호},
    ).fetchall()


@router.get("/api/works/{work_id}/testers", response_model=list[TesterOut])
def list_testers(work_id: int, conn: Conn, me: CurrentUser) -> list[dict]:
    load_work_for_actor(conn, work_id, me)
    return conn.execute(
        'SELECT a."번호" AS 계정_번호, a."아이디", a."닉네임", t."부여일시" '
        'FROM "테스터" t JOIN "계정" a ON a."번호" = t."계정_번호" '
        'WHERE t."작품_번호" = %s ORDER BY t."번호"',
        (work_id,),
    ).fetchall()


@router.post("/api/works/{work_id}/testers", status_code=status.HTTP_201_CREATED, response_model=TesterOut)
def add_tester(work_id: int, body: TesterIn, conn: Conn, me: CurrentUser) -> dict:
    work, _, _ = load_work_for_actor(conn, work_id, me, lock=True)
    target = conn.execute(
        'SELECT "번호", "아이디", "닉네임", "상태" FROM "계정" WHERE "아이디" = %s', (body.아이디,)
    ).fetchone()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "해당 아이디의 계정이 없습니다")
    if target["상태"] != "정상":
        raise HTTPException(status.HTTP_409_CONFLICT, "이용할 수 없는 계정입니다")
    if target["번호"] == work["계정_번호"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "제작자는 이미 방을 만들 수 있습니다")
    row = conn.execute(
        'INSERT INTO "테스터" ("작품_번호", "계정_번호") VALUES (%s, %s) '
        'ON CONFLICT ("작품_번호", "계정_번호") DO NOTHING RETURNING "부여일시"',
        (work_id, target["번호"]),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 테스터입니다")
    return {"계정_번호": target["번호"], "아이디": target["아이디"], "닉네임": target["닉네임"], "부여일시": row["부여일시"]}


@router.delete("/api/works/{work_id}/testers/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_tester(work_id: int, account_id: int, conn: Conn, me: CurrentUser) -> None:
    load_work_for_actor(conn, work_id, me, lock=True)
    deleted = conn.execute(
        'DELETE FROM "테스터" WHERE "작품_번호" = %s AND "계정_번호" = %s RETURNING 1', (work_id, account_id)
    ).fetchone()
    if deleted is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "테스터가 아닙니다")
