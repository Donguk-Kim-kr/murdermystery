"""기본 진행단계 등록 (app/common_phases.py)."""
import psycopg
import pytest

from app.common_phases import register
from app.default_phases import COMMON_PHASES


@pytest.fixture
def conn(test_dbname):
    with psycopg.connect(f"dbname={test_dbname}", autocommit=True) as c:
        yield c
        # 같은 시험 DB 를 쓰는 다른 시험이 "공통 항목이 없다"고 보고 있으므로 만든 것을 치운다
        c.execute('ALTER TABLE "진행단계" DISABLE TRIGGER USER')
        c.execute('DELETE FROM "진행단계" WHERE "계정_번호" IS NULL')
        c.execute('ALTER TABLE "진행단계" ENABLE TRIGGER USER')


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
    conn.execute("""UPDATE "진행단계" SET "규칙" = '{"스크립트": "낡은 스크립트"}'::jsonb WHERE 계정_번호 IS NULL AND 이름 = '공통 스토리'""")
    conn.execute('ALTER TABLE "진행단계" ENABLE TRIGGER USER')
    assert register(conn) == ["공통 스토리: 새 버전 v2"]
    versions = [r[0] for r in conn.execute('SELECT 버전 FROM "진행단계" WHERE 계정_번호 IS NULL AND 이름 = \'공통 스토리\' ORDER BY 버전').fetchall()]
    assert versions == [1, 2]


def test_the_old_prologue_phase_is_renamed_in_place(conn):
    """이름이 바뀐 기본 진행단계는 옛 이름의 항목을 새 이름으로 바꾼다(작품이 가리키는 번호는 그대로)."""
    register(conn)
    number = conn.execute("""SELECT 번호 FROM "진행단계" WHERE 계정_번호 IS NULL AND 이름 = '공통 스토리'""").fetchone()[0]
    conn.execute("""UPDATE "진행단계" SET 이름 = '프롤로그' WHERE 번호 = %s""", (number,))
    done = register(conn)
    assert done[0] == "프롤로그: 이름을 공통 스토리로 바꿈"
    assert conn.execute('SELECT 이름 FROM "진행단계" WHERE 번호 = %s', (number,)).fetchone()[0] == "공통 스토리"
    assert conn.execute("""SELECT count(*) FROM "진행단계" WHERE 계정_번호 IS NULL AND 이름 = '프롤로그'""").fetchone()[0] == 0


def test_reset_keeps_only_the_latest_content_as_v1_and_keeps_placed_cards(conn, client, headers):
    from app.common_phases import reset_to_v1

    register(conn)
    conn.execute('ALTER TABLE "진행단계" DISABLE TRIGGER USER')
    conn.execute("""UPDATE "진행단계" SET "규칙" = '{"스크립트": "낡은 스크립트"}'::jsonb WHERE 계정_번호 IS NULL AND 이름 = '조사'""")
    conn.execute('ALTER TABLE "진행단계" ENABLE TRIGGER USER')
    register(conn)                                                      # 조사 v2 가 생긴다
    old, new = [r[0] for r in conn.execute("""SELECT 번호 FROM "진행단계" WHERE 계정_번호 IS NULL AND 이름 = '조사' ORDER BY 버전""").fetchall()]
    w = client.post("/api/works", headers=headers, json={"제목": "작품"}).json()["번호"]
    phase = client.post(f"/api/works/{w}/content/phases", headers=headers, json={"진행시간": 20}).json()["순서"]
    for lib in (old, new):                                              # 같은 단계의 옛 버전과 새 버전이 한 페이즈에 함께 놓여 있다
        res = client.post(f"/api/works/{w}/content/phase-steps", headers=headers, json={"진행순서_순서": phase, "진행단계_번호": lib})
        assert res.status_code == 201, res.text

    done = reset_to_v1(conn)
    assert any(line.startswith("조사: 버전 2개 → v1") for line in done)
    rows = conn.execute("""SELECT 번호, 버전, 규칙 FROM "진행단계" WHERE 계정_번호 IS NULL AND 이름 = '조사'""").fetchall()
    assert len(rows) == 1 and rows[0][1] == 1 and "낡은" not in rows[0][2]["스크립트"]      # 최신 내용이 v1 로 남는다
    cards = conn.execute('SELECT 진행단계_번호 FROM "진행구성" WHERE 작품_번호 = %s', (w,)).fetchall()
    assert cards == [(rows[0][0],)]                                     # 카드는 새 v1 로 이어지고 중복은 하나만 남는다
    assert conn.execute("""SELECT count(*) FROM "진행단계" WHERE 계정_번호 IS NULL AND 이름 LIKE '%정리 전%'""").fetchone()[0] == 0
    assert reset_to_v1(conn) == []                                      # 다시 해도 바뀌지 않는다
    conn.execute('DELETE FROM "작품" WHERE 번호 = %s', (w,))
