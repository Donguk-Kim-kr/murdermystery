"""작품 내부 `순서` 번호 부여 (docs/DB_RULES.md B13).

작품별로 1부터 차례로 부여한다. 이미 다른 행이 `(작품_번호, X_순서)` 복합 FK 로 가리키는 번호는
(ON UPDATE CASCADE 가 없으므로) 바꿀 수 없다. 그래서 기존 번호는 건드리지 않고 새 항목에 다음 번호만 붙인다.

호출하는 쪽이 같은 트랜잭션에서 `lock_work()` 로 작품 행을 먼저 잠가야 동시 요청이 같은 번호를 받지 않는다.
"""
from psycopg import Connection, sql

# 식별자는 SQL 에 직접 끼워 넣으므로 허용 목록으로만 받는다.
ORDERED_TABLES = frozenset({
    "진행순서", "기믹적용", "인물", "장소", "단서", "증언", "조합", "사건",
    "엔딩분기", "후일담", "타임라인", "투표", "미디어",
})


def next_order(conn: Connection, table: str, work_id: int) -> int:
    if table not in ORDERED_TABLES:
        raise ValueError(f"순서를 쓰는 테이블이 아닙니다: {table}")
    row = conn.execute(
        sql.SQL('SELECT COALESCE(MAX("순서"), 0) + 1 AS n FROM {} WHERE "작품_번호" = %s').format(sql.Identifier(table)),
        (work_id,),
    ).fetchone()
    return row["n"]
