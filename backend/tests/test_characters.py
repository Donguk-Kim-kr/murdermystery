from concurrent.futures import ThreadPoolExecutor

import pytest


@pytest.fixture
def work(client, headers):
    res = client.post("/api/works", headers=headers, json={"제목": "저택의 비밀"})
    return res.json()


def add(client, headers, wid, name="인물", **kw):
    res = client.post(f"/api/works/{wid}/characters", headers=headers, json={"이름": name, **kw})
    assert res.status_code == 201, res.text
    return res.json()


def capacity(client, headers, wid):
    return client.get(f"/api/works/{wid}", headers=headers).json()["최대인원"]


def test_orders_start_at_one_and_increase_per_work(client, headers, work):
    other = client.post("/api/works", headers=headers, json={"제목": "다른 작품"}).json()
    assert [add(client, headers, work["번호"], f"p{i}")["순서"] for i in range(3)] == [1, 2, 3]
    # 다른 작품은 다시 1부터 시작한다.
    assert add(client, headers, other["번호"])["순서"] == 1


def test_list_is_ordered_by_order(client, headers, work):
    for name in ("가", "나", "다"):
        add(client, headers, work["번호"], name)
    res = client.get(f"/api/works/{work['번호']}/characters", headers=headers)
    assert [(c["순서"], c["이름"]) for c in res.json()] == [(1, "가"), (2, "나"), (3, "다")]


def test_capacity_stays_one_with_no_characters_then_follows_player_count(client, headers, work):
    wid = work["번호"]
    assert capacity(client, headers, wid) == 1  # 인물 0명: 임시 1
    add(client, headers, wid, "A")
    assert capacity(client, headers, wid) == 1
    add(client, headers, wid, "B")
    add(client, headers, wid, "C")
    assert capacity(client, headers, wid) == 3


def test_npc_is_not_counted(client, headers, work):
    wid = work["번호"]
    add(client, headers, wid, "A")
    add(client, headers, wid, "B")
    add(client, headers, wid, "피해자", NPC=True)
    assert capacity(client, headers, wid) == 2


def test_only_npc_characters_keeps_temporary_one(client, headers, work):
    add(client, headers, work["번호"], "피해자", NPC=True)
    assert capacity(client, headers, work["번호"]) == 1


def test_toggling_npc_recomputes_capacity(client, headers, work):
    wid = work["번호"]
    for n in "ABC":
        add(client, headers, wid, n)
    assert capacity(client, headers, wid) == 3
    assert client.patch(f"/api/works/{wid}/characters/3", headers=headers, json={"NPC": True}).status_code == 200
    assert capacity(client, headers, wid) == 2
    client.patch(f"/api/works/{wid}/characters/3", headers=headers, json={"NPC": False})
    assert capacity(client, headers, wid) == 3


def test_npc_toggle_below_min_players_is_rejected_and_rolled_back(client, headers, work):
    wid = work["번호"]
    for n in "ABC":
        add(client, headers, wid, n)
    assert client.patch(f"/api/works/{wid}", headers=headers, json={"최소인원": 3}).status_code == 200
    res = client.patch(f"/api/works/{wid}/characters/3", headers=headers, json={"NPC": True})
    assert res.status_code == 409
    assert client.get(f"/api/works/{wid}/characters/3", headers=headers).json()["NPC"] is False
    assert capacity(client, headers, wid) == 3


def test_min_players_can_be_raised_up_to_player_count(client, headers, work):
    wid = work["번호"]
    for n in "ABCD":
        add(client, headers, wid, n)
    assert client.patch(f"/api/works/{wid}", headers=headers, json={"최소인원": 4}).status_code == 200
    assert client.patch(f"/api/works/{wid}", headers=headers, json={"최소인원": 5}).status_code == 409


def test_update_character_fields(client, headers, work):
    wid = work["번호"]
    add(client, headers, wid, "A", 직업="의사")
    res = client.patch(f"/api/works/{wid}/characters/1", headers=headers, json={"이름": "A2", "직업": None, "범인": True})
    body = res.json()
    assert (body["이름"], body["직업"], body["범인"], body["순서"]) == ("A2", None, True, 1)


def test_required_character_fields_cannot_be_blanked(client, headers, work):
    wid = work["번호"]
    add(client, headers, wid, "A")
    for patch in ({"이름": None}, {"서사": None}, {"NPC": None}, {"이름": ""}):
        assert client.patch(f"/api/works/{wid}/characters/1", headers=headers, json=patch).status_code == 422


def test_other_users_cannot_touch_characters(client, new_user):
    owner, other = new_user(), new_user()
    wid = client.post("/api/works", headers=owner, json={"제목": "t"}).json()["번호"]
    add(client, owner, wid, "A")
    assert client.get(f"/api/works/{wid}/characters", headers=other).status_code == 404
    assert client.post(f"/api/works/{wid}/characters", headers=other, json={"이름": "침입"}).status_code == 404
    assert client.patch(f"/api/works/{wid}/characters/1", headers=other, json={"이름": "침입"}).status_code == 404
    assert client.get(f"/api/works/{wid}/characters/1", headers=other).status_code == 404


def test_missing_character_is_404(client, headers, work):
    assert client.get(f"/api/works/{work['번호']}/characters/7", headers=headers).status_code == 404


def test_concurrent_creates_get_distinct_consecutive_orders(client, headers, work):
    wid = work["번호"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: client.post(
            f"/api/works/{wid}/characters", headers=headers, json={"이름": f"p{i}"}), range(8)))
    assert [r.status_code for r in results] == [201] * 8
    assert sorted(r.json()["순서"] for r in results) == list(range(1, 9))
    assert capacity(client, headers, wid) == 8


def test_delete_character_updates_capacity_and_is_blocked_while_referenced(client, headers):
    wid = client.post("/api/works", headers=headers, json={"제목": "w"}).json()["번호"]
    base = f"/api/works/{wid}/characters"
    a = client.post(base, headers=headers, json={"이름": "A"}).json()["순서"]
    b = client.post(base, headers=headers, json={"이름": "B"}).json()["순서"]
    assert client.get(f"/api/works/{wid}", headers=headers).json()["최대인원"] == 2
    # 단서가 가리키는 인물은 지울 수 없다
    clue = client.post(f"/api/works/{wid}/content/clues", headers=headers, json={"이름": "c", "인물_순서": b})
    assert clue.status_code == 201
    assert client.delete(f"{base}/{b}", headers=headers).status_code == 409
    assert client.delete(f"{base}/{a}", headers=headers).status_code == 204
    assert client.get(f"/api/works/{wid}", headers=headers).json()["최대인원"] == 1
    assert client.delete(f"{base}/{a}", headers=headers).status_code == 404


def test_delete_character_cannot_drop_below_min_players(client, headers):
    wid = client.post("/api/works", headers=headers, json={"제목": "w"}).json()["번호"]
    base = f"/api/works/{wid}/characters"
    for n in "ABC":
        client.post(base, headers=headers, json={"이름": n})
    assert client.patch(f"/api/works/{wid}", headers=headers, json={"최소인원": 3}).status_code == 200
    assert client.delete(f"{base}/3", headers=headers).status_code == 409
    assert len(client.get(base, headers=headers).json()) == 3


def test_other_users_cannot_delete_a_character(client, new_user):
    owner, other = new_user(), new_user()
    wid = client.post("/api/works", headers=owner, json={"제목": "w"}).json()["번호"]
    c = client.post(f"/api/works/{wid}/characters", headers=owner, json={"이름": "A"}).json()["순서"]
    assert client.delete(f"/api/works/{wid}/characters/{c}", headers=other).status_code == 404


def test_intro_line_is_optional_editable_and_clearable(client, make_account):
    headers = make_account().headers
    work = client.post("/api/works", headers=headers, json={"제목": "소개"}).json()
    wid = work["번호"]
    made = client.post(f"/api/works/{wid}/characters", headers=headers, json={"이름": "의사", "서사": "과거"})
    assert made.status_code == 201 and made.json()["소개"] is None
    res = client.patch(f"/api/works/{wid}/characters/1", headers=headers, json={"소개": "마을의 의사입니다."})
    assert res.status_code == 200 and res.json()["소개"] == "마을의 의사입니다."
    assert client.get(f"/api/works/{wid}/characters/1", headers=headers).json()["소개"] == "마을의 의사입니다."
    assert client.patch(f"/api/works/{wid}/characters/1", headers=headers, json={"소개": None}).json()["소개"] is None
    too_long = client.patch(f"/api/works/{wid}/characters/1", headers=headers, json={"소개": "가" * 1001})
    assert too_long.status_code == 422


def test_story_parts_are_saved_with_ids_and_restored(client, headers, work):
    wid = work["번호"]
    made = client.post(f"/api/works/{wid}/characters", headers=headers, json={"이름": "의사", "서사_부분": [{"본문": "첫째"}, {"본문": "둘째"}]})
    assert made.status_code == 201, made.text
    parts = made.json()["서사_부분"]
    assert [p["본문"] for p in parts] == ["첫째", "둘째"] and all(len(p["ID"]) == 6 for p in parts)
    assert parts[0]["ID"] != parts[1]["ID"]
    assert "@@MMPART:" in made.json()["서사"]                         # 저장된 글에는 표기가 들어 있고
    got = client.get(f"/api/works/{wid}/characters/1", headers=headers).json()
    assert got["서사_부분"] == parts                                  # 다시 읽어도 같은 부분과 ID
    # 같은 ID 로 다시 보내면 ID 가 유지되고, ID 없는 부분은 새로 만든다
    patched = client.patch(f"/api/works/{wid}/characters/1", headers=headers, json={"서사_부분": [{"ID": parts[1]["ID"], "본문": "둘째 수정"}, {"본문": "새 서사"}]})
    assert patched.status_code == 200
    kept = patched.json()["서사_부분"]
    assert kept[0] == {"ID": parts[1]["ID"], "본문": "둘째 수정"} and kept[1]["본문"] == "새 서사" and kept[1]["ID"] not in {p["ID"] for p in parts}


def test_story_limit_shrinks_as_parts_increase(client, headers, work):
    wid = work["번호"]
    url = f"/api/works/{wid}/characters"
    assert client.post(url, headers=headers, json={"이름": "가", "서사_부분": [{"본문": "가" * 10000}]}).status_code == 201
    two = client.post(url, headers=headers, json={"이름": "나", "서사_부분": [{"본문": "가" * 5001}, {"본문": "나"}]})
    assert two.status_code == 422 and "5000자" in two.json()["detail"]
    assert client.post(url, headers=headers, json={"이름": "다", "서사_부분": [{"본문": "가" * 5000}, {"본문": "나" * 5000}]}).status_code == 201
    six = client.post(url, headers=headers, json={"이름": "라", "서사_부분": [{"본문": str(i)} for i in range(6)]})
    assert six.status_code == 422 and "5개까지" in six.json()["detail"]
    empty = client.post(url, headers=headers, json={"이름": "마", "서사_부분": [{"본문": "  "}]})
    assert empty.status_code == 422


def test_story_rejects_reserved_marker_and_conflicting_input(client, headers, work):
    wid = work["번호"]
    url = f"/api/works/{wid}/characters"
    assert client.post(url, headers=headers, json={"이름": "가", "서사_부분": [{"본문": "앞 @@MMPART:abcdef@@ 뒤"}]}).status_code == 422
    assert client.post(url, headers=headers, json={"이름": "가", "서사": "본문", "서사_부분": [{"본문": "다른"}]}).status_code == 422
    # 옛 방식(글 한 덩어리)은 부분 하나로 저장되고 ID 가 붙는다
    old = client.post(url, headers=headers, json={"이름": "나", "서사": "옛 서사"}).json()
    assert [p["본문"] for p in old["서사_부분"]] == ["옛 서사"] and len(old["서사_부분"][0]["ID"]) == 6

