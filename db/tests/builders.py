"""테스트용 INSERT 빌더. 컬럼명=값 형태로 간단히 행을 넣고 번호를 돌려받는다."""
from __future__ import annotations

import json
from typing import Any

from helpers import PgTestCase


class Raw:
    """따옴표 처리 없이 그대로 SQL 에 삽입할 식 (예: Raw("CURRENT_TIMESTAMP"))."""

    def __init__(self, sql: str):
        self.sql = sql


def lit(v: Any) -> str:
    if isinstance(v, Raw):
        return v.sql
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (dict, list)):
        return "'" + json.dumps(v, ensure_ascii=False).replace("'", "''") + "'::jsonb"
    return "'" + str(v).replace("'", "''") + "'"


def insert_sql(table: str, cols: dict[str, Any], returning: bool = True) -> str:
    names = ", ".join(f'"{c}"' for c in cols)
    values = ", ".join(lit(v) for v in cols.values())
    sql = f'INSERT INTO "{table}" ({names}) VALUES ({values})'
    return sql + (' RETURNING "번호"' if returning else "")


class Builders(PgTestCase):
    """PgTestCase + 테이블별 최소 행 빌더. 테스트 클래스의 공통 부모로 쓴다."""

    __test__ = False

    # ---- 일반 -----------------------------------------------------------
    def ins(self, table: str, **cols) -> int:
        return int(self.db.val(insert_sql(table, cols)))

    def ins_fails(self, table: str, contains: str | None = None, **cols) -> str:
        return self.db.fails(insert_sql(table, cols, returning=False), contains)

    def count(self, table: str, where: str = "TRUE") -> int:
        return int(self.db.val(f'SELECT count(*) FROM "{table}" WHERE {where}'))

    # ---- 제작용 콘텐츠 최소 행 -------------------------------------------------
    def step(self, w, n=1, **kw):
        return self.ins("진행순서", 작품_번호=w, 순서=n, **kw)

    def character(self, w, n=1, **kw):
        kw.setdefault("이름", f"인물{n}")
        kw.setdefault("서사", "서사")
        return self.ins("인물", 작품_번호=w, 순서=n, **kw)

    def place(self, w, n=1, **kw):
        kw.setdefault("이름", f"장소{n}")
        return self.ins("장소", 작품_번호=w, 순서=n, **kw)

    def clue(self, w, n=1, **kw):
        kw.setdefault("이름", f"단서{n}")
        return self.ins("단서", 작품_번호=w, 순서=n, **kw)

    def witness(self, w, n=1, **kw):
        kw.setdefault("이름", "증언")
        kw.setdefault("공개이름", "지나가던 사람")
        kw.setdefault("내용", "내용")
        return self.ins("증언", 작품_번호=w, 순서=n, **kw)

    def combo(self, w, n=1, **kw):
        kw.setdefault("이름", f"조합{n}")
        return self.ins("조합", 작품_번호=w, 순서=n, **kw)

    def incident(self, w, n=1, **kw):
        return self.ins("사건", 작품_번호=w, 순서=n, **kw)

    def phase(self, **kw):
        kw.setdefault("이름", f"토론{self.db.n()}")   # ("계정_번호","이름","버전") UNIQUE 라서 매번 다른 이름
        kw.setdefault("규칙", {"any": "value"})
        kw.setdefault("설명", "설명")
        return self.ins("진행단계", **kw)

    def gimmick(self, **kw):
        kw.setdefault("이름", f"기믹{self.db.n()}")   # ("계정_번호","이름","버전") UNIQUE 라서 매번 다른 이름
        kw.setdefault("조건", {"any": "value"})
        kw.setdefault("결과", {"any": "value"})
        return self.ins("기믹", **kw)

    def applied_gimmick(self, w, n=1, step=1, gimmick=None, **kw):
        gimmick = gimmick or self.gimmick()
        return self.ins("기믹적용", 작품_번호=w, 순서=n, 기믹_번호=gimmick, 진행순서_순서=step, **kw)

    def vote(self, w, n=1, step=1, **kw):
        kw.setdefault("이름", "투표")
        kw.setdefault("내용", "내용")
        kw.setdefault("규칙", {"any": "value"})
        return self.ins("투표", 작품_번호=w, 순서=n, 진행순서_순서=step, **kw)

    def media(self, w, n=1, **kw):
        kw.setdefault("유형", "이미지")
        kw.setdefault("경로", f"private/{w}/{n}.png")
        return self.ins("미디어", 작품_번호=w, 순서=n, **kw)

    # ---- 확정 버전 / 게임 실행 ---------------------------------------------
    def version(self, w, ver="1.0", scenario=None, **kw):
        scenario = {"snapshot": True} if scenario is None else scenario
        return self.ins("버전", 작품_번호=w, 버전=ver, 시나리오=scenario, **kw)

    def room(self, w=None, ver="1.0", account=None, code=None, **kw):
        """방은 작품과 확정 버전을 가진다 (1방 1게임). w 를 생략하면 작품과 버전을 새로 만든다."""
        if w is None:
            w = self.work()
            self.version(w, ver)
        account = account or self.account()
        code = code or f"CODE{self.db.n()}"
        return self.ins("방", 계정_번호=account, 입장코드=code, 작품_번호=w, 버전_버전=ver, **kw)

    def game(self, room, w, ver="1.0", **kw):
        return self.ins("진행", 방_번호=room, 작품_번호=w, 버전_버전=ver, **kw)

    def participant(self, w, game, account=None, **kw):
        account = account or self.account()
        return self.ins("참여", 작품_번호=w, 진행_번호=game, 계정_번호=account, **kw)

    def playable_game(self, ver="1.0"):
        """작품 + 확정 버전 + 방 + 진행을 한 번에 만든다. (work, game) 반환"""
        w = self.work()
        self.version(w, ver)
        g = self.game(self.room(w, ver), w, ver)
        return w, g
