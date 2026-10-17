"""게임 시작 (docs/ENGINE_DESIGN.md 1-1, docs/ENGINE_SPEC.md)."""
import psycopg
import pytest


@pytest.fixture
def db(test_dbname):
    with psycopg.connect(f"dbname={test_dbname}", autocommit=True) as conn:
        yield conn


@pytest.fixture
def make_game_work(client):
    """진짜 확정 버전(스냅샷)이 있는 작품: 플레이어 인물 players 명, 페이즈 phases 개."""

    def make(owner, players=3, phases=3, npcs=0):
        wid = client.post("/api/works", headers=owner.headers, json={"제목": "시험 작품"}).json()["번호"]
        for i in range(players):
            assert client.post(f"/api/works/{wid}/characters", headers=owner.headers, json={"이름": f"p{i}"}).status_code == 201
        for i in range(npcs):
            assert client.post(f"/api/works/{wid}/characters", headers=owner.headers, json={"이름": f"n{i}", "NPC": True}).status_code == 201
        for i in range(phases):
            res = client.post(f"/api/works/{wid}/phases/insert", headers=owner.headers, json={"position": i + 1})
            assert res.status_code == 201, res.text
        res = client.post(f"/api/works/{wid}/confirm", headers=owner.headers, json={})
        assert res.status_code == 201, res.text
        return wid

    return make


def create_room(client, who, wid, **kw):
    res = client.post("/api/rooms", headers=who.headers, json={"작품_번호": wid, **kw})
    assert res.status_code == 201, res.text
    return res.json()


def join(client, who, code):
    res = client.post("/api/rooms/join", headers=who.headers, json={"입장코드": code})
    assert res.status_code == 200, res.text


def start(client, who):
    return client.post("/api/rooms/me/start", headers=who.headers)


def full_room(client, make_account, make_game_work, players=3, **kw):
    host = make_account()
    wid = make_game_work(host, players=players, **kw)
    room = create_room(client, host, wid)
    others = [make_account() for _ in range(players - 1)]
    for o in others:
        join(client, o, room["입장코드"])
    return host, others, room, wid


def test_start_creates_progress_and_participations(client, make_account, make_game_work, db):
    host, others, room, wid = full_room(client, make_account, make_game_work)
    res = start(client, host)
    assert res.status_code == 200, res.text
    body = res.json()
    assert [p["계정_번호"] for p in body["플레이어"]] == [host.number] + [o.number for o in others]   # 입장한 순서
    assert body["관전자"] == []

    r = db.execute('SELECT "상태" FROM "방" WHERE "번호" = %s', (room["번호"],)).fetchone()
    assert r[0] == "진행"
    prog = db.execute('SELECT "번호", "버전_버전", "진행순서_순서" FROM "진행" WHERE "방_번호" = %s', (room["번호"],)).fetchone()
    assert prog[0] == body["진행_번호"] and prog[1] == "1.0"
    first_slot = db.execute('SELECT min("순서") FROM "진행순서" WHERE "작품_번호" = %s', (wid,)).fetchone()[0]
    assert prog[2] == first_slot == body["현재_페이즈_순서"]
    parts = db.execute('SELECT "계정_번호", "인물_순서" FROM "참여" WHERE "진행_번호" = %s ORDER BY "번호"', (prog[0],)).fetchall()
    assert {p[0] for p in parts} == {host.number, *(o.number for o in others)}
    assert all(p[1] is None for p in parts)            # 인물은 캐릭터 선택에서 정해진다


def test_start_registers_game_in_memory(client, make_account, make_game_work):
    host, others, room, _ = full_room(client, make_account, make_game_work)
    assert start(client, host).status_code == 200
    game = client.app.state.games.get(room["번호"])
    assert game is not None and game.host_id == host.number
    assert list(game.players) == [host.number] + [o.number for o in others]
    assert game.phase_index == 0 and game.state_version == 1 and len(game.phases) == 3
    assert client.app.state.games.of_account(others[0].number) is game


def test_only_host_can_start(client, make_account, make_game_work):
    host, others, room, _ = full_room(client, make_account, make_game_work)
    res = start(client, others[0])
    assert res.status_code == 403
    assert client.app.state.games.get(room["번호"]) is None


def test_player_count_must_match_characters(client, make_account, make_game_work, db):
    host = make_account()
    wid = make_game_work(host, players=3)
    room = create_room(client, host, wid)
    join(client, make_account(), room["입장코드"])           # 방장 + 1명 = 2명, 인물은 3명
    res = start(client, host)
    assert res.status_code == 409 and "2명" in res.json()["detail"] and "3명" in res.json()["detail"]
    assert db.execute('SELECT "상태" FROM "방" WHERE "번호" = %s', (room["번호"],)).fetchone()[0] == "대기"
    assert db.execute('SELECT count(*) FROM "진행" WHERE "방_번호" = %s', (room["번호"],)).fetchone()[0] == 0


def test_npc_characters_are_not_counted(client, make_account, make_game_work):
    host, _, room, _ = full_room(client, make_account, make_game_work, players=2, npcs=1)
    assert start(client, host).status_code == 200


def test_host_who_does_not_play_becomes_observer(client, make_account, make_game_work):
    host = make_account()
    wid = make_game_work(host, players=2)
    room = create_room(client, host, wid, 방장_참여=False)
    a, b = make_account(), make_account()
    join(client, a, room["입장코드"])
    join(client, b, room["입장코드"])
    res = start(client, host)
    assert res.status_code == 200, res.text
    body = res.json()
    assert [p["계정_번호"] for p in body["플레이어"]] == [a.number, b.number]
    assert [o["계정_번호"] for o in body["관전자"]] == [host.number]


def test_cannot_start_twice(client, make_account, make_game_work, db):
    host, _, room, _ = full_room(client, make_account, make_game_work)
    assert start(client, host).status_code == 200
    assert start(client, host).status_code == 409
    assert db.execute('SELECT count(*) FROM "진행" WHERE "방_번호" = %s', (room["번호"],)).fetchone()[0] == 1


def test_start_without_room(client, make_account):
    assert start(client, make_account()).status_code == 404


def test_cannot_join_after_start(client, make_account, make_game_work):
    host, _, room, _ = full_room(client, make_account, make_game_work)
    assert start(client, host).status_code == 200
    late = client.post("/api/rooms/join", headers=make_account().headers, json={"입장코드": room["입장코드"]})
    assert late.status_code == 409
