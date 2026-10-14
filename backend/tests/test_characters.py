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
