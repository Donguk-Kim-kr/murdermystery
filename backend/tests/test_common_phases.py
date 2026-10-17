"""기본 진행단계 등록 (app/common_phases.py)."""
import psycopg
import pytest

from app.common_phases import register
from app.default_phases import COMMON_PHASES


@pytest.fixture
def conn(test_dbname):
    with psycopg.connect(f"dbname={test_dbname}", autocommit=True) as c:
        yield c


def test_registers_every_common_phase_once_and_is_repeatable(conn):
    first = register(conn)
    assert len(first) == len(COMMON_PHASES) and all("새로 만듦 v1" in line for line in first)
    assert register(conn) == []                                           # 다시 실행해도 아무것도 바뀌지 않는다
    rows = conn.execute('SELECT 이름, 버전, 규칙 FROM "진행단계" WHERE 계정_번호 IS NULL ORDER BY 이름').fetchall()
    assert sorted(r[0] for r in rows) == sorted(n for n, *_ in COMMON_PHASES) and all(r[1] == 1 for r in rows)
    assert all("실행" in r[2]["스크립트"] for r in rows)


def test_changed_script_becomes_a_new_version_and_other_accounts_items_are_untouched(conn):
    register(conn)
    conn.execute('ALTER TABLE "진행단계" DISABLE TRIGGER USER')
    conn.execute("""UPDATE "진행단계" SET "규칙" = '{"스크립트": "낡은 스크립트"}'::jsonb WHERE 계정_번호 IS NULL AND 이름 = '프롤로그'""")
    conn.execute('ALTER TABLE "진행단계" ENABLE TRIGGER USER')
    assert register(conn) == ["프롤로그: 새 버전 v2"]
    versions = [r[0] for r in conn.execute('SELECT 버전 FROM "진행단계" WHERE 계정_번호 IS NULL AND 이름 = \'프롤로그\' ORDER BY 버전').fetchall()]
    assert versions == [1, 2]
