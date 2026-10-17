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


# ---- 상태 조회 (1-2) ----------------------------------------------------------------------

def state(client, who):
    return client.get("/api/game/me/state", headers=who.headers)


def test_state_for_player(client, make_account, make_game_work):
    host, others, room, _ = full_room(client, make_account, make_game_work)
    assert start(client, host).status_code == 200
    res = state(client, others[0])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["상태_버전"] == 1
    assert body["나"] == {"계정_번호": others[0].number, "역할": "플레이어", "인물_순서": None, "방장": False, "진행_권한": False}
    assert body["페이즈"]["위치"] == 1 and body["페이즈"]["전체"] == 3 and body["페이즈"]["진행시간"] == 30
    assert [p["계정_번호"] for p in body["플레이어"]] == [host.number] + [o.number for o in others]
    assert [c["이름"] for c in body["인물"]] == ["p0", "p1", "p2"]
    assert all(c["선택한_계정"] is None for c in body["인물"])


def test_host_has_progress_authority(client, make_account, make_game_work):
    host, _, _, _ = full_room(client, make_account, make_game_work)
    start(client, host)
    me = state(client, host).json()["나"]
    assert me["방장"] is True and me["진행_권한"] is True


def test_observer_state(client, make_account, make_game_work):
    host = make_account()
    wid = make_game_work(host, players=2)
    room = create_room(client, host, wid, 방장_참여=False)
    for _ in range(2):
        join(client, make_account(), room["입장코드"])
    start(client, host)
    me = state(client, host).json()["나"]
    assert me["역할"] == "관전자" and me["인물_순서"] is None and me["진행_권한"] is True


def test_state_never_contains_private_character_data(client, make_account, test_dbname):
    host = make_account()
    wid = client.post("/api/works", headers=host.headers, json={"제목": "비밀 시험"}).json()["번호"]
    for i in range(2):
        r = client.post(f"/api/works/{wid}/characters", headers=host.headers, json={
            "이름": f"인물{i}", "직업": "의사", "서사": f"개인서사_{i}_XYZ", "비밀": f"비밀값_{i}_XYZ", "능력": "능력_XYZ",
            "목표": "목표_XYZ", "타임라인": "타임라인_XYZ", "범인": i == 0,
        })
        assert r.status_code == 201, r.text
    assert client.post(f"/api/works/{wid}/phases/insert", headers=host.headers, json={"position": 1}).status_code == 201
    assert client.post(f"/api/works/{wid}/confirm", headers=host.headers, json={}).status_code == 201
    room = create_room(client, host, wid)
    other = make_account()
    join(client, other, room["입장코드"])
    assert start(client, host).status_code == 200
    for who in (host, other):
        text = state(client, who).text
        assert "XYZ" not in text                    # 서사, 비밀, 능력, 목표, 타임라인
        assert "범인" not in text
        assert "의사" in text                       # 공개 정보(직업)는 보인다


def test_state_requires_game(client, make_account, make_game_work):
    assert state(client, make_account()).status_code == 404
    host, others, room, _ = full_room(client, make_account, make_game_work)
    assert state(client, others[0]).status_code == 404       # 시작 전에는 없다
    start(client, host)
    assert state(client, others[0]).status_code == 200


def test_state_version_is_stable_between_reads(client, make_account, make_game_work):
    host, _, _, _ = full_room(client, make_account, make_game_work)
    start(client, host)
    assert state(client, host).json()["상태_버전"] == state(client, host).json()["상태_버전"] == 1
