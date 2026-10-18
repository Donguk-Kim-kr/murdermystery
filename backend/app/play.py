"""플레이공간의 작품 목록 API.

내가 방을 만들 수 있는 작품을 모아 보여 준다: 공개된 작품 + 내가 비공개 플레이할 수 있는 작품(내 작품·테스터로 지정받은 작품).
방을 만들려면 확정된 버전이 있어야 하므로 확정 버전이 없는 작품은 뺀다.
인물·단서 같은 내용(범인·비밀 포함)은 내려 주지 않는다.
"""
from pydantic import BaseModel
from fastapi import APIRouter

from .auth import CurrentUser
from .db import Conn
from .testers import _TESTABLE

router = APIRouter(prefix="/api/play-works", tags=["play"])


class PlayWorkOut(BaseModel):
    번호: int
    제목: str
    시놉시스: str
    장르: str
    최소인원: int
    최대인원: int
    예상시간: str
    제작자: str
    비공개플레이: bool


@router.get("", response_model=list[PlayWorkOut])
def play_works(conn: Conn, me: CurrentUser) -> list[dict]:
    return conn.execute(
        'SELECT w."번호", w."제목", w."시놉시스", w."장르", w."최소인원", w."최대인원", w."예상시간", '
        'a."닉네임" AS "제작자", NOT w."공개여부" AS "비공개플레이" '
        'FROM "작품" w JOIN "계정" a ON a."번호" = w."계정_번호" '
        'LEFT JOIN "테스터" t ON t."작품_번호" = w."번호" AND t."계정_번호" = %(me)s '
        f'WHERE w."상태" <> \'삭제\' AND EXISTS (SELECT 1 FROM "버전" v WHERE v."작품_번호" = w."번호") AND (w."공개여부" OR ({_TESTABLE})) '
        'ORDER BY w."번호" DESC',
        {"me": me.계정.번호},
    ).fetchall()
