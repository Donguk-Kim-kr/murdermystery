"""확정(confirm.py): 검사, 스냅샷 내용, 버전 번호, 소유자만."""
import psycopg
import pytest


def work(client, headers, **kw):
    res = client.post("/api/works", headers=headers, json={"제목": "저택의 비밀", **kw})
    assert res.status_code == 201, res.text
    return res.json()["번호"]


def post(client, headers, w, path, **body):
    res = client.post(f"/api/works/{w}/content/{path}", headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def character(client, headers, w, **kw):
    res = client.post(f"/api/works/{w}/characters", headers=headers, json={"이름": "A", **kw})
    assert res.status_code == 201, res.text
    return res.json()


def check(client, headers, w):
    res = client.get(f"/api/works/{w}/confirm/check", headers=headers)
    assert res.status_code == 200
    return res.json()


def confirm(client, headers, w, **body):
    return client.post(f"/api/works/{w}/confirm", headers=headers, json=body)


def ready(client, headers):
    w = work(client, headers)
    character(client, headers, w)
    post(client, headers, w, "phases", 진행시간=10)
    return w


def snapshot(test_dbname, w, version):
    with psycopg.connect(f"dbname={test_dbname}") as conn:
        return conn.execute('SELECT "시나리오" FROM "버전" WHERE "작품_번호" = %s AND "버전" = %s', (w, version)).fetchone()[0]


def test_empty_work_cannot_be_confirmed_but_reports_why(client, headers):
    w = work(client, headers)
    res = check(client, headers, w)
    assert len(res["errors"]) == 2 and res["다음버전"] == "1.0"
    bad = confirm(client, headers, w)
    assert bad.status_code == 422 and "인물" in bad.json()["detail"] and "페이즈" in bad.json()["detail"]
    assert client.get(f"/api/works/{w}/versions", headers=headers).json() == []


def test_npc_only_work_is_not_ready(client, headers):
    w = work(client, headers)
    character(client, headers, w, NPC=True)
    post(client, headers, w, "phases", 진행시간=10)
    assert any("플레이어" in e for e in check(client, headers, w)["errors"])


def test_warnings_do_not_block(client, headers):
    w = ready(client, headers)
    res = check(client, headers, w)
    assert res["errors"] == [] and any("범인" in x for x in res["warnings"]) and any("진행단계가 없습니다" in x for x in res["warnings"])
    assert confirm(client, headers, w).status_code == 201


def test_confirm_makes_versions_and_updates_latest(client, headers):
    w = ready(client, headers)
    first = confirm(client, headers, w, 변경사항="처음 확정")
    assert first.status_code == 201 and first.json()["버전"] == "1.0" and first.json()["변경사항"] == "처음 확정"
    assert check(client, headers, w)["다음버전"] == "2.0"
    assert confirm(client, headers, w).json()["버전"] == "2.0"
    assert [v["버전"] for v in client.get(f"/api/works/{w}/versions", headers=headers).json()] == ["2.0", "1.0"]
    assert client.get(f"/api/works/{w}", headers=headers).json()["확정버전_있음"] is True


def test_snapshot_is_a_frozen_copy_of_the_work(client, headers, test_dbname):
    w = work(client, headers, 시놉시스="비 오는 밤", 공통스토리="모두 모였다")
    a = character(client, headers, w, 이름="집사")["순서"]
    b = character(client, headers, w, 이름="요리사", NPC=True)["순서"]
    place = post(client, headers, w, "places", 이름="서재")
    post(client, headers, w, "clues", 이름="편지", 장소_순서=place["순서"], 인물_순서=a)
    ph = post(client, headers, w, "phases", 진행시간=20)
    post(client, headers, w, "timelines", 설명="자정에 사건", 시작시간="2026-01-01T00:00:00")
    lib = client.post("/api/library/phases", headers=headers, json={"이름": "조사", "설명": "d", "규칙": {}}).json()
    post(client, headers, w, "phase-steps", 진행순서_순서=ph["순서"], 진행단계_번호=lib["번호"])
    assert confirm(client, headers, w).status_code == 201
    snap = snapshot(test_dbname, w, "1.0")
    assert snap["형식버전"] == 1
    assert snap["작품"]["제목"] == "저택의 비밀" and snap["작품"]["공통스토리"] == "모두 모였다"
    assert [c["이름"] for c in snap["인물"]] == ["집사", "요리사"] and snap["인물"][1]["NPC"] is True
    assert snap["단서"] == [{"순서": 1, "이름": "편지", "내용": None, "기능": None, "인물_순서": a, "장소_순서": place["순서"]}]
    assert snap["진행순서"] == [{"순서": 1, "이름": None, "진행시간": 20, "표시이름": lib["이름"]}]
    assert snap["진행구성"] == [{"진행순서_순서": 1, "진행단계_번호": lib["번호"], "설정": None, "표시이름": lib["이름"]}]
    assert "번호" not in snap["진행구성"][0] and "작품_번호" not in snap["장소"][0]
    assert snap["타임라인"][0]["시작시간"].startswith("2026-01-01T00:00:00")
    # 라이브러리는 값 사본
    [copied] = snap["라이브러리"]["진행단계"]
    assert copied["이름"] == lib["이름"] and copied["버전"] == lib["버전"] and copied["규칙"] == lib["규칙"]
    assert snap["라이브러리"]["기믹"] == []
    # 확정 뒤 고쳐도 스냅샷은 그대로
    client.patch(f"/api/works/{w}/content/places/{place['순서']}", headers=headers, json={"이름": "바뀐 이름"})
    assert snapshot(test_dbname, w, "1.0")["장소"][0]["이름"] == "서재"
    confirm(client, headers, w)
    assert snapshot(test_dbname, w, "2.0")["장소"][0]["이름"] == "바뀐 이름"
    _ = b


def test_deleted_library_links_are_dropped_with_a_warning(client, headers, test_dbname):
    w = ready(client, headers)
    gim = client.post("/api/library/gimmicks", headers=headers, json={"이름": "독 발견", "조건": {}, "결과": {}}).json()
    use = post(client, headers, w, "gimmick-uses", 기믹_번호=gim["번호"], 진행순서_순서=1)
    assert snap_has_gimmick(client, headers, w, test_dbname, expect=True)
    client.delete(f"/api/library/gimmicks/{gim['번호']}", headers=headers)
    res = check(client, headers, w)
    assert any("독 발견" in x and "삭제" in x for x in res["warnings"])
    confirm(client, headers, w)
    snap = snapshot(test_dbname, w, "2.0")
    assert snap["기믹적용"] == [] and snap["라이브러리"]["기믹"] == []
    # 연결 자체는 작업 중인 작품에 남아 있다
    assert [u["순서"] for u in client.get(f"/api/works/{w}/content/gimmick-uses", headers=headers).json()] == [use["순서"]]


def snap_has_gimmick(client, headers, w, test_dbname, *, expect):
    confirm(client, headers, w)
    snap = snapshot(test_dbname, w, "1.0")
    return bool(snap["기믹적용"]) == expect and len(snap["라이브러리"]["기믹"]) == (1 if expect else 0)


def test_only_the_owner_can_check_confirm_or_list(client, headers, new_user):
    w = ready(client, headers)
    other = new_user()
    assert client.get(f"/api/works/{w}/confirm/check", headers=other).status_code == 404
    assert confirm(client, other, w).status_code == 404
    assert client.get(f"/api/works/{w}/versions", headers=other).status_code == 404
    assert client.get(f"/api/works/{w}/versions").status_code == 401




def test_next_version_uses_the_numeric_part_not_text_order(client, headers, confirm):
    w = ready(client, headers)
    confirm(w, "9.0")
    confirm(w, "10.0")  # 글자 순으로는 "9.0" 이 더 크다
    assert check(client, headers, w)["다음버전"] == "11.0"


def test_broken_phase_script_blocks_confirm_with_a_reason(client, headers):
    w = ready(client, headers)
    lib = client.post("/api/library/phases", headers=headers, json={"이름": "깨진 카드", "설명": "x", "규칙": {"스크립트": "def 실행(카드):\n    몰라()"}})
    assert lib.status_code == 201, lib.text
    post(client, headers, w, "phase-steps", 진행순서_순서=1, 진행단계_번호=lib.json()["번호"])
    result = check(client, headers, w)
    assert len(result["errors"]) == 1
    assert "깨진 카드" in result["errors"][0] and "알 수 없는 이름" in result["errors"][0] and "2번째 줄" in result["errors"][0]
    assert confirm(client, headers, w).status_code == 422


def test_working_scripts_and_cards_without_scripts_do_not_block_confirm(client, headers):
    w = ready(client, headers)
    good = client.post("/api/library/phases", headers=headers, json={"이름": "정상", "설명": "x", "규칙": {"스크립트": "def 실행(카드):\n    모두.보이기(글('안내', '안녕'))"}}).json()
    plain = client.post("/api/library/phases", headers=headers, json={"이름": "스크립트 없음", "설명": "x", "규칙": {}}).json()
    post(client, headers, w, "phase-steps", 진행순서_순서=1, 진행단계_번호=good["번호"])
    post(client, headers, w, "phase-steps", 진행순서_순서=1, 진행단계_번호=plain["번호"])
    assert check(client, headers, w)["errors"] == []
    assert confirm(client, headers, w).status_code == 201


def test_warns_when_a_card_picks_a_story_part_a_character_does_not_have(client, headers):
    w = ready(client, headers)
    client.patch(f"/api/works/{w}/characters/1", headers=headers, json={"서사_부분": [{"본문": "하나"}]})
    lib = client.post("/api/library/phases", headers=headers, json={"이름": "프로필", "설명": "x", "규칙": {}}).json()
    step = post(client, headers, w, "phase-steps", 진행순서_순서=1, 진행단계_번호=lib["번호"], 설정={"개인서사공개": {"1": [1, 3]}})
    result = check(client, headers, w)
    assert result["errors"] == []
    assert any("서사 3" in text and "서사는 1개" in text for text in result["warnings"])
    # 고르지 않은 번호이거나 있는 번호만 고르면 경고하지 않는다
    client.patch(f"/api/works/{w}/content/phase-steps/{step['번호']}", headers=headers, json={"설정": {"개인서사공개": {"1": [1]}}})
    assert not any("서사 3" in text for text in check(client, headers, w)["warnings"])


def test_content_bundle_tells_which_settings_a_card_script_uses_and_story_counts(client, headers):
    w = ready(client, headers)
    client.patch(f"/api/works/{w}/characters/1", headers=headers, json={"서사_부분": [{"본문": "하나"}, {"본문": "둘"}]})
    lib = client.post("/api/library/phases", headers=headers, json={
        "이름": "프로필", "설명": "x", "규칙": {"스크립트": "def 실행(카드):\n    공개 = 카드.설정.get('개인서사공개', {})"},
    }).json()
    post(client, headers, w, "phase-steps", 진행순서_순서=1, 진행단계_번호=lib["번호"])
    bundle = client.get(f"/api/works/{w}/content", headers=headers).json()
    ref = bundle["library"]["phases"][str(lib["번호"])]
    assert ref["사용설정"] == ["개인서사공개"] and "규칙" not in ref
    assert bundle["characters"][0]["서사_부분수"] == 2 and "서사" not in bundle["characters"][0]
