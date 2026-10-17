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
    assert me["역할"] == "관전자" and me["인물_순서"] is None and me["방장"] is True
    assert me["진행_권한"] is False                       # 일반 관전의 방장은 진행 권한이 플레이어에게 간다


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


# ---- 캐릭터 배정 (1-3) --------------------------------------------------------------------

def confirm_pick(client, who, slot):
    return client.post("/api/game/me/confirm", headers=who.headers, json={"인물_순서": slot})


def slots(client, who):
    return [c["순서"] for c in state(client, who).json()["인물"]]


def test_confirm_assigns_character_and_updates_progress(client, make_account, make_game_work, db):
    host, others, room, _ = full_room(client, make_account, make_game_work)
    start(client, host)
    first = slots(client, host)[0]
    res = confirm_pick(client, others[0], first)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["나"]["인물_순서"] == first and body["상태_버전"] == 2
    assert body["선택_완료"] == {"완료": 1, "전체": 3}
    mine = [p for p in body["플레이어"] if p["계정_번호"] == others[0].number][0]
    assert mine["인물_이름"] == "p0"
    assert [c["선택한_계정"] for c in body["인물"]][0] == others[0].number
    row = db.execute('SELECT "인물_순서" FROM "참여" WHERE "계정_번호" = %s AND "진행_번호" = (SELECT "번호" FROM "진행" WHERE "방_번호" = %s)',
                     (others[0].number, room["번호"])).fetchone()
    assert row[0] == first


def test_other_players_see_who_took_a_character(client, make_account, make_game_work):
    host, others, _, _ = full_room(client, make_account, make_game_work)
    start(client, host)
    first = slots(client, host)[0]
    confirm_pick(client, others[0], first)
    seen = state(client, host).json()
    assert seen["선택_완료"]["완료"] == 1
    assert seen["인물"][0]["선택한_계정"] == others[0].number
    assert seen["나"]["인물_순서"] is None            # 내 인물은 아직 없다


def test_same_character_cannot_be_taken_twice(client, make_account, make_game_work, db):
    host, others, room, _ = full_room(client, make_account, make_game_work)
    start(client, host)
    first = slots(client, host)[0]
    assert confirm_pick(client, others[0], first).status_code == 200
    res = confirm_pick(client, others[1], first)
    assert res.status_code == 409 and "이미 다른 사람" in res.json()["detail"]
    assert state(client, others[1]).json()["나"]["인물_순서"] is None
    assert db.execute('SELECT count(*) FROM "참여" WHERE "인물_순서" = %s AND "진행_번호" = (SELECT "번호" FROM "진행" WHERE "방_번호" = %s)',
                      (first, room["번호"])).fetchone()[0] == 1


def test_confirm_is_final(client, make_account, make_game_work):
    host, others, _, _ = full_room(client, make_account, make_game_work)
    start(client, host)
    a, b = slots(client, host)[:2]
    assert confirm_pick(client, others[0], a).status_code == 200
    res = confirm_pick(client, others[0], b)
    assert res.status_code == 409 and "이미" in res.json()["detail"]
    assert state(client, others[0]).json()["나"]["인물_순서"] == a


def test_unknown_character_and_non_players_are_rejected(client, make_account, make_game_work):
    host = make_account()
    wid = make_game_work(host, players=2, npcs=1)
    room = create_room(client, host, wid, 방장_참여=False)
    a, b = make_account(), make_account()
    join(client, a, room["입장코드"])
    join(client, b, room["입장코드"])
    start(client, host)
    assert confirm_pick(client, host, slots(client, a)[0]).status_code == 403          # 관전자
    assert confirm_pick(client, a, 99999).status_code == 422
    npc_slot = max(c["순서"] for c in client.get(f"/api/works/{wid}/characters", headers=host.headers).json())
    assert npc_slot not in slots(client, a)                                            # NPC 는 고르는 목록에 없다
    assert confirm_pick(client, a, npc_slot).status_code == 422
    assert confirm_pick(client, make_account(), 1).status_code == 404                  # 게임에 없는 사람


def test_concurrent_confirms_for_same_character_one_wins(client, make_account, make_game_work, db):
    from concurrent.futures import ThreadPoolExecutor

    host, others, room, _ = full_room(client, make_account, make_game_work)
    start(client, host)
    first = slots(client, host)[0]
    who = [host, *others]
    with ThreadPoolExecutor(max_workers=3) as pool:
        codes = sorted(pool.map(lambda w: confirm_pick(client, w, first).status_code, who))
    assert codes == [200, 409, 409]
    assert db.execute('SELECT count(*) FROM "참여" WHERE "인물_순서" = %s AND "진행_번호" = (SELECT "번호" FROM "진행" WHERE "방_번호" = %s)',
                      (first, room["번호"])).fetchone()[0] == 1


def test_all_players_can_confirm_distinct_characters(client, make_account, make_game_work):
    host, others, _, _ = full_room(client, make_account, make_game_work)
    start(client, host)
    for who, slot in zip([host, *others], slots(client, host)):
        assert confirm_pick(client, who, slot).status_code == 200
    final = state(client, host).json()
    assert final["선택_완료"] == {"완료": 3, "전체": 3} and final["상태_버전"] == 4


# ---- 페이즈 전환과 시간 (1-4) ---------------------------------------------------------------

@pytest.fixture
def clock(client):
    reg = client.app.state.games
    original = reg.clock
    t = {"now": 1000.0}
    reg.clock = lambda: t["now"]
    yield t
    reg.clock = original


def advance(client, who):
    return client.post("/api/game/me/advance", headers=who.headers)


def pause(client, who, value):
    return client.post("/api/game/me/pause", headers=who.headers, json={"일시정지": value})


def started(client, make_account, make_game_work, **kw):
    host, others, room, wid = full_room(client, make_account, make_game_work, **kw)
    assert start(client, host).status_code == 200
    return host, others, room, wid


def test_advance_moves_to_next_phase_and_saves_it(client, make_account, make_game_work, db):
    host, _, room, wid = started(client, make_account, make_game_work)
    before = state(client, host).json()
    res = advance(client, host)
    assert res.status_code == 200, res.text
    after = res.json()
    assert after["페이즈"]["위치"] == 2 and after["상태_버전"] == before["상태_버전"] + 1
    slots_ = [r[0] for r in db.execute('SELECT "순서" FROM "진행순서" WHERE "작품_번호" = %s ORDER BY "순서"', (wid,)).fetchall()]
    saved = db.execute('SELECT "진행순서_순서" FROM "진행" WHERE "방_번호" = %s', (room["번호"],)).fetchone()[0]
    assert saved == slots_[1]


def test_only_authority_can_advance_or_pause(client, make_account, make_game_work):
    host, others, _, _ = started(client, make_account, make_game_work)
    assert advance(client, others[0]).status_code == 403
    assert pause(client, others[0], True).status_code == 403
    assert state(client, host).json()["페이즈"]["위치"] == 1


def test_cannot_advance_past_last_phase(client, make_account, make_game_work):
    host, _, _, _ = started(client, make_account, make_game_work, phases=2)
    assert advance(client, host).status_code == 200
    res = advance(client, host)
    assert res.status_code == 409 and "마지막" in res.json()["detail"]


def test_card_condition_blocks_advance_with_message(client, make_account, make_game_work):
    host, others, room, _ = started(client, make_account, make_game_work)
    game = client.app.state.games.get(room["번호"])
    game.advance_conditions.append(
        lambda g: "캐릭터 선택이 완료되지 않았습니다." if any(p.character is None for p in g.players.values()) else None
    )
    res = advance(client, host)
    assert res.status_code == 409 and res.json()["detail"] == "캐릭터 선택이 완료되지 않았습니다."
    assert state(client, host).json()["페이즈"]["위치"] == 1
    for who, slot in zip([host, *others], slots(client, host)):
        confirm_pick(client, who, slot)
    assert advance(client, host).status_code == 200


def test_time_runs_pauses_and_resets_on_advance(client, make_account, make_game_work, clock):
    host, _, _, _ = started(client, make_account, make_game_work)
    t0 = state(client, host).json()["시간"]
    assert t0["남은_초"] == 1800 and t0["일시정지"] is False and t0["시간_종료"] is False and t0["서버_시각"] == 1000.0
    clock["now"] += 100
    assert state(client, host).json()["시간"]["남은_초"] == 1700
    v = state(client, host).json()["상태_버전"]
    res = pause(client, host, True)
    assert res.json()["시간"]["일시정지"] is True and res.json()["상태_버전"] == v + 1
    clock["now"] += 500                                              # 멈춘 동안은 흐르지 않는다
    assert state(client, host).json()["시간"]["남은_초"] == 1700
    assert pause(client, host, True).json()["상태_버전"] == v + 1    # 같은 값이면 버전이 오르지 않는다
    pause(client, host, False)
    clock["now"] += 100
    assert state(client, host).json()["시간"]["남은_초"] == 1600
    clock["now"] += 2000
    expired = state(client, host).json()["시간"]
    assert expired["남은_초"] == 0 and expired["시간_종료"] is True
    assert state(client, host).json()["페이즈"]["위치"] == 1         # 시간이 끝나도 방장이 넘기기 전에는 넘어가지 않는다
    nxt = advance(client, host).json()
    assert nxt["페이즈"]["위치"] == 2 and nxt["시간"]["남은_초"] == 1800 and nxt["시간"]["시간_종료"] is False


def test_early_advance_and_advance_while_paused_are_allowed(client, make_account, make_game_work):
    host, _, _, _ = started(client, make_account, make_game_work)
    assert advance(client, host).status_code == 200                  # 시간이 남아 있어도
    pause(client, host, True)
    res = advance(client, host)                                      # 일시정지 중이어도
    assert res.status_code == 200 and res.json()["시간"]["일시정지"] is False   # 새 페이즈의 시간은 다시 흐른다


def test_zero_minutes_means_no_time_limit(client, make_account, make_game_work, clock):
    host = make_account()
    wid = client.post("/api/works", headers=host.headers, json={"제목": "무제한"}).json()["번호"]
    client.post(f"/api/works/{wid}/characters", headers=host.headers, json={"이름": "a"})
    assert client.post(f"/api/works/{wid}/phases/insert", headers=host.headers, json={"position": 1, "진행시간": 0}).status_code == 201
    assert client.post(f"/api/works/{wid}/confirm", headers=host.headers, json={}).status_code == 201
    room = create_room(client, host, wid)
    assert start(client, host).status_code == 200
    clock["now"] += 99999
    t = state(client, host).json()["시간"]
    assert t["남은_초"] is None and t["시간_종료"] is False


# ---- 진행 권한과 이탈 (1-5) -----------------------------------------------------------------

def authority(client, who):
    return state(client, who).json()["권한"]


def test_host_holds_authority_by_default(client, make_account, make_game_work, clock):
    host, others, _, _ = started(client, make_account, make_game_work)
    a = authority(client, others[0])
    assert a["계정_번호"] == host.number and a["임시"] is False


def test_authority_moves_down_the_join_order_and_comes_back(client, make_account, make_game_work, clock):
    host, others, _, _ = started(client, make_account, make_game_work)
    clock["now"] += 50                                  # 유예(45초)를 넘긴다. 방장만 상태를 확인하지 않는다
    state(client, others[1])                            # 3번 플레이어는 계속 접속
    # 2번 플레이어(others[0])도 이탈한 상태로 두면 3번이 임시로 갖는다
    a = authority(client, others[1])
    assert a["계정_번호"] == others[1].number and a["임시"] is True
    assert state(client, others[1]).json()["나"]["진행_권한"] is True
    state(client, others[0])                            # 2번이 돌아오면 2번이 임시로 갖는다
    assert authority(client, others[0])["계정_번호"] == others[0].number
    state(client, host)                                 # 방장이 돌아오면 방장이 되돌려 받는다
    back = authority(client, host)
    assert back["계정_번호"] == host.number and back["임시"] is False


def test_temporary_holder_can_advance_while_host_is_away(client, make_account, make_game_work, clock):
    host, others, _, _ = started(client, make_account, make_game_work)
    clock["now"] += 50                                  # 방장이 상태를 확인하지 않은 채 유예를 넘긴다
    state(client, others[0])
    assert authority(client, others[0])["계정_번호"] == others[0].number
    res = advance(client, others[0])
    assert res.status_code == 200 and res.json()["페이즈"]["위치"] == 2


def test_player_seat_survives_being_away(client, make_account, make_game_work, clock):
    host, others, _, _ = started(client, make_account, make_game_work)
    slot = slots(client, host)[0]
    confirm_pick(client, others[0], slot)
    clock["now"] += 500
    state(client, host)
    seen = state(client, host).json()
    mine = [p for p in seen["플레이어"] if p["계정_번호"] == others[0].number][0]
    assert mine["인물_순서"] == slot and mine["접속중"] is False


def test_observer_host_hands_authority_to_first_player(client, make_account, make_game_work, clock):
    host = make_account()
    wid = make_game_work(host, players=2)
    room = create_room(client, host, wid, 방장_참여=False)
    a, b = make_account(), make_account()
    join(client, a, room["입장코드"])
    join(client, b, room["입장코드"])
    start(client, host)
    holder = authority(client, host)
    assert holder["계정_번호"] == a.number and holder["임시"] is True          # 입장 순서의 첫 플레이어
    assert state(client, host).json()["나"]["진행_권한"] is False
    assert advance(client, host).status_code == 403
    assert advance(client, a).status_code == 200


def test_host_can_hand_authority_to_specific_player_and_take_it_back(client, make_account, make_game_work, clock):
    host, others, _, _ = started(client, make_account, make_game_work)
    res = client.post("/api/game/me/authority", headers=host.headers, json={"계정_번호": others[1].number})
    assert res.status_code == 200, res.text
    assert res.json()["권한"] == {"계정_번호": others[1].number, "닉네임": res.json()["권한"]["닉네임"], "임시": False}
    assert advance(client, host).status_code == 403
    assert advance(client, others[1]).status_code == 200
    back = client.post("/api/game/me/authority", headers=host.headers, json={"계정_번호": host.number})
    assert back.json()["권한"]["계정_번호"] == host.number


def test_only_host_can_hand_over_and_only_to_players(client, make_account, make_game_work):
    host, others, _, _ = started(client, make_account, make_game_work)
    assert client.post("/api/game/me/authority", headers=others[0].headers, json={"계정_번호": others[1].number}).status_code == 403
    assert client.post("/api/game/me/authority", headers=host.headers, json={"계정_번호": 999999}).status_code == 422


# ---- 실시간 알림 SSE (1-6) ------------------------------------------------------------------
# TestClient 는 끝나지 않는 스트림을 다룰 수 없어서, 앱을 ASGI 로 직접 호출해 한 건씩 읽는다.

import asyncio
import json as _json


class SseConnection:
    """앱의 SSE 엔드포인트에 ASGI 로 직접 연결해 한 건씩 읽는 시험용 연결."""

    def __init__(self, app, headers: dict, path: str = "/api/game/me/events"):
        self.app, self.headers, self.path = app, headers, path
        self.out: asyncio.Queue = asyncio.Queue()
        self.disconnected = asyncio.Event()
        self.sent_request = False
        self.task = None
        self.status = None
        self.response_headers = {}
        self.buffer = ""

    async def receive(self):
        if not self.sent_request:
            self.sent_request = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self.disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(self, message):
        await self.out.put(message)

    async def open(self):
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "path": self.path,
            "raw_path": self.path.encode(), "query_string": b"", "root_path": "", "scheme": "http",
            "server": ("test", 80), "client": ("test", 1),
            "headers": [(k.lower().encode(), v.encode()) for k, v in self.headers.items()],
        }
        self.task = asyncio.create_task(self.app(scope, self.receive, self.send))
        start = await asyncio.wait_for(self.out.get(), 10)
        assert start["type"] == "http.response.start"
        self.status = start["status"]
        self.response_headers = {k.decode(): v.decode() for k, v in start["headers"]}
        return self

    async def event(self, timeout: float = 10):
        """다음 SSE 한 건 (이벤트 이름, 데이터). 신호용 주석(`: ping`)은 건너뛴다."""
        while True:
            while "\n\n" in self.buffer:
                block, self.buffer = self.buffer.split("\n\n", 1)
                name, data = None, None
                for line in block.split("\n"):
                    if line.startswith("event:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        data = _json.loads(line.split(":", 1)[1].strip())
                if name is not None:
                    return name, data
            msg = await asyncio.wait_for(self.out.get(), timeout)
            if msg["type"] == "http.response.body":
                self.buffer += msg.get("body", b"").decode()
                if not msg.get("more_body", False) and "\n\n" not in self.buffer:
                    raise AssertionError("스트림이 끝났다")

    async def close(self):
        self.disconnected.set()
        try:
            await asyncio.wait_for(self.task, 10)
        except asyncio.TimeoutError:
            self.task.cancel()
            raise AssertionError("연결을 닫아도 스트림이 끝나지 않았다")


def run(coro):
    return asyncio.run(coro)


def test_events_require_auth_and_game(client, make_account):
    assert client.get("/api/game/me/events").status_code == 401
    assert client.get("/api/game/me/events", headers=make_account().headers).status_code == 404


def test_events_send_current_version_then_changes(client, make_account, make_game_work):
    host, others, _, _ = started(client, make_account, make_game_work)
    first = slots(client, host)[0]

    async def scenario():
        conn = await SseConnection(client.app, others[0].headers).open()
        try:
            assert conn.status == 200
            assert conn.response_headers["content-type"].startswith("text/event-stream")
            assert conn.response_headers["cache-control"] == "no-cache"
            assert await conn.event() == ("version", {"상태_버전": 1})                  # 연결하자마자 지금 버전
            await asyncio.to_thread(confirm_pick, client, host, first)                   # 다른 사람의 행동
            assert await conn.event() == ("version", {"상태_버전": 2})
            await asyncio.to_thread(advance, client, host)
            assert await conn.event() == ("version", {"상태_버전": 3})
        finally:
            await conn.close()

    run(scenario())


def test_events_carry_only_the_version(client, make_account, make_game_work):
    host, _, _, _ = started(client, make_account, make_game_work)

    async def scenario():
        conn = await SseConnection(client.app, host.headers).open()
        try:
            _, data = await conn.event()
            assert set(data) == {"상태_버전"}
        finally:
            await conn.close()

    run(scenario())


def test_game_continues_and_listener_is_released_when_connection_closes(client, make_account, make_game_work):
    host, others, room, _ = started(client, make_account, make_game_work)
    game = client.app.state.games.get(room["번호"])

    async def scenario():
        for who in (others[0], host, others[1]):
            conn = await SseConnection(client.app, who.headers).open()
            await conn.event()
            assert len(game._listeners) == 1
            await conn.close()
            assert game._listeners == []                                                 # 연결 정보가 정리된다

    run(scenario())
    assert advance(client, host).status_code == 200                                      # 연결이 없어도 게임은 진행된다


def test_several_listeners_all_get_the_change(client, make_account, make_game_work):
    host, others, _, _ = started(client, make_account, make_game_work)

    async def scenario():
        conns = [await SseConnection(client.app, w.headers).open() for w in (host, *others)]
        try:
            for c in conns:
                assert await c.event() == ("version", {"상태_버전": 1})
            await asyncio.to_thread(advance, client, host)
            for c in conns:
                assert await c.event() == ("version", {"상태_버전": 2})
        finally:
            for c in conns:
                await c.close()

    run(scenario())


def test_open_connection_counts_as_present_and_closed_one_does_not(client, make_account, make_game_work, clock, monkeypatch):
    import app.game as game_module

    monkeypatch.setattr(game_module, "KEEPALIVE_SECONDS", 0.05)       # 신호를 자주 보내게 한다
    host, others, room, _ = started(client, make_account, make_game_work)
    game = client.app.state.games.get(room["번호"])

    async def scenario():
        conn = await SseConnection(client.app, others[0].headers).open()
        try:
            await conn.event()
            for _ in range(3):
                clock["now"] += 40                                    # 연결된 동안은 유예(45초)를 여러 번 넘겨도 접속 중이다
                await asyncio.sleep(0.2)
                assert not game.away(others[0].number)
        finally:
            await conn.close()
        clock["now"] += 50                                            # 연결을 닫고 유예가 지나면 이탈이다
        assert game.away(others[0].number)

    run(scenario())


# ---- 재접속 (1-7) -----------------------------------------------------------------------------

def relogin(client, who):
    """같은 계정으로 새로 로그인한다(브라우저를 껐다 켠 것처럼 새 토큰을 쓴다)."""
    token = client.post("/api/auth/login", json={"아이디": who.login_id, "패스워드": "password123", "접속환경": "PC"}).json()["토큰"]
    return type(who)({"Authorization": f"Bearer {token}"}, who.number, who.login_id)


def test_reconnect_with_new_login_restores_same_state(client, make_account, make_game_work, clock):
    host, others, _, _ = started(client, make_account, make_game_work)
    slot = slots(client, host)[1]
    confirm_pick(client, others[0], slot)
    advance(client, host)
    clock["now"] += 123
    pause(client, host, True)
    before = state(client, others[0]).json()
    again = relogin(client, others[0])
    after = state(client, again).json()
    assert after == before                                              # 같은 상태 그대로
    assert after["나"]["인물_순서"] == slot and after["페이즈"]["위치"] == 2 and after["시간"]["일시정지"] is True


def test_returning_player_is_present_again(client, make_account, make_game_work, clock):
    host, others, room, _ = started(client, make_account, make_game_work)
    game = client.app.state.games.get(room["번호"])
    clock["now"] += 500
    assert game.away(others[0].number)
    state(client, relogin(client, others[0]))
    assert not game.away(others[0].number)


def test_events_after_missed_changes_start_at_latest_version(client, make_account, make_game_work):
    host, others, _, _ = started(client, make_account, make_game_work)
    slot = slots(client, host)[0]

    async def scenario():
        conn = await SseConnection(client.app, others[0].headers).open()
        assert await conn.event() == ("version", {"상태_버전": 1})
        await conn.close()                                              # 화면이 꺼져 연결이 끊겼다
        await asyncio.to_thread(confirm_pick, client, host, slot)       # 그동안 두 번 바뀌었다
        await asyncio.to_thread(advance, client, host)
        conn = await SseConnection(client.app, others[0].headers).open()   # 다시 연결
        try:
            assert await conn.event() == ("version", {"상태_버전": 3})   # 놓친 변화 없이 최신 버전부터
            assert state(client, others[0]).json()["상태_버전"] == 3
        finally:
            await conn.close()

    run(scenario())


def test_state_version_only_increases(client, make_account, make_game_work):
    host, others, _, _ = started(client, make_account, make_game_work)
    seen = [state(client, host).json()["상태_버전"]]
    for slot, who in zip(slots(client, host), [host, *others]):
        confirm_pick(client, who, slot)
        seen.append(state(client, host).json()["상태_버전"])
    advance(client, host)
    seen.append(state(client, host).json()["상태_버전"])
    assert seen == sorted(seen) and len(set(seen)) == len(seen)


def test_failed_actions_do_not_change_version(client, make_account, make_game_work):
    host, others, _, _ = started(client, make_account, make_game_work)
    v = state(client, host).json()["상태_버전"]
    assert confirm_pick(client, others[0], 99999).status_code == 422
    assert advance(client, others[0]).status_code == 403
    assert client.post("/api/game/me/authority", headers=others[0].headers, json={"계정_번호": host.number}).status_code == 403
    assert state(client, host).json()["상태_버전"] == v


# ---- 게임 종료와 방 종료 (1-8) ------------------------------------------------------------------

def end_now(client, room_id):
    from app.engine import end_game

    game = client.app.state.games.get(room_id)
    with client.app.state.pool.connection() as conn:
        end_game(game, lambda: conn.execute('UPDATE "진행" SET "상태" = \'종료\' WHERE "번호" = %s', (game.id,)))


def room_state(db, room_id):
    return db.execute('SELECT "상태" FROM "방" WHERE "번호" = %s', (room_id,)).fetchone()[0]


def test_end_game_marks_progress_ended_and_changes_state(client, make_account, make_game_work, db):
    host, _, room, _ = started(client, make_account, make_game_work)
    v = state(client, host).json()["상태_버전"]
    assert state(client, host).json()["종료"] is False
    end_now(client, room["번호"])
    after = state(client, host).json()
    assert after["종료"] is True and after["상태_버전"] == v + 1
    end_now(client, room["번호"])                                         # 두 번 불러도 한 번만 바뀐다
    assert state(client, host).json()["상태_버전"] == v + 1
    prog = db.execute('SELECT "상태", "종료일시" FROM "진행" WHERE "방_번호" = %s', (room["번호"],)).fetchone()
    assert prog[0] == "종료" and prog[1] is not None
    assert room_state(db, room["번호"]) == "진행"                          # 방은 바로 닫히지 않는다


def test_actions_are_rejected_after_game_ends(client, make_account, make_game_work):
    host, others, room, _ = started(client, make_account, make_game_work)
    end_now(client, room["번호"])
    assert advance(client, host).status_code == 409
    assert confirm_pick(client, others[0], slots(client, host)[0]).status_code == 409


def test_room_closes_six_hours_after_game_ends(client, make_account, make_game_work, db):
    from app.main import sweep_rooms

    host, _, room, _ = started(client, make_account, make_game_work)
    end_now(client, room["번호"])
    sweep_rooms(client.app)
    assert room_state(db, room["번호"]) == "진행"                          # 방금 끝났다
    db.execute('UPDATE "진행" SET "종료일시" = CURRENT_TIMESTAMP - interval \'5 hours\' WHERE "방_번호" = %s', (room["번호"],))
    sweep_rooms(client.app)
    assert room_state(db, room["번호"]) == "진행"                          # 5시간: 아직
    db.execute('UPDATE "진행" SET "종료일시" = CURRENT_TIMESTAMP - interval \'7 hours\' WHERE "방_번호" = %s', (room["번호"],))
    sweep_rooms(client.app)
    assert room_state(db, room["번호"]) == "종료"                          # 6시간 지났다
    assert client.app.state.games.get(room["번호"]) is None                # 메모리의 게임도 정리된다
    assert state(client, host).status_code == 404


def test_unfinished_game_room_has_twelve_hour_cap(client, make_account, make_game_work, db):
    from app.main import sweep_rooms

    host, _, room, _ = started(client, make_account, make_game_work)
    db.execute('UPDATE "방" SET "상태변경일시" = CURRENT_TIMESTAMP - interval \'11 hours\' WHERE "번호" = %s', (room["번호"],))
    sweep_rooms(client.app)
    assert room_state(db, room["번호"]) == "진행"
    db.execute('UPDATE "방" SET "상태변경일시" = CURRENT_TIMESTAMP - interval \'13 hours\' WHERE "번호" = %s', (room["번호"],))
    sweep_rooms(client.app)
    assert room_state(db, room["번호"]) == "종료"


# ---- 시간이 끝난 뒤 자동 진행 (1-4b) ---------------------------------------------------------------

def set_auto(client, who, value):
    return client.post("/api/game/me/settings", headers=who.headers, json={"자동_진행": value})


def tick(client):
    from app.main import tick_games

    tick_games(client.app)


def test_auto_advance_is_off_by_default(client, make_account, make_game_work, clock):
    host, _, _, _ = started(client, make_account, make_game_work)
    assert state(client, host).json()["설정"] == {"자동_진행": False}
    clock["now"] += 99999
    tick(client)
    assert state(client, host).json()["페이즈"]["위치"] == 1            # 시간이 지나도 방장이 넘기기 전에는 넘어가지 않는다


def test_only_host_can_change_auto_advance(client, make_account, make_game_work):
    host, others, _, _ = started(client, make_account, make_game_work)
    assert set_auto(client, others[0], True).status_code == 403
    res = set_auto(client, host, True)
    assert res.status_code == 200 and res.json()["설정"] == {"자동_진행": True}


def test_auto_advance_moves_on_when_time_is_up(client, make_account, make_game_work, clock, db):
    host, _, room, wid = started(client, make_account, make_game_work)
    set_auto(client, host, True)
    v = state(client, host).json()["상태_버전"]
    clock["now"] += 1799
    tick(client)
    assert state(client, host).json()["페이즈"]["위치"] == 1            # 아직 1초 남았다
    clock["now"] += 2
    tick(client)
    after = state(client, host).json()
    assert after["페이즈"]["위치"] == 2 and after["시간"]["남은_초"] == 1800 and after["상태_버전"] == v + 1
    saved = db.execute('SELECT "진행순서_순서" FROM "진행" WHERE "방_번호" = %s', (room["번호"],)).fetchone()[0]
    assert saved == [r[0] for r in db.execute('SELECT "순서" FROM "진행순서" WHERE "작품_번호" = %s ORDER BY "순서"', (wid,)).fetchall()][1]


def test_auto_advance_waits_while_paused(client, make_account, make_game_work, clock):
    host, _, _, _ = started(client, make_account, make_game_work)
    set_auto(client, host, True)
    clock["now"] += 1700
    pause(client, host, True)
    clock["now"] += 99999
    tick(client)
    assert state(client, host).json()["페이즈"]["위치"] == 1
    pause(client, host, False)
    clock["now"] += 101
    tick(client)
    assert state(client, host).json()["페이즈"]["위치"] == 2


def test_auto_advance_respects_card_condition_and_last_phase(client, make_account, make_game_work, clock):
    host, others, room, _ = started(client, make_account, make_game_work, phases=2)
    game = client.app.state.games.get(room["번호"])
    game.advance_conditions.append(
        lambda g: "캐릭터 선택이 완료되지 않았습니다." if any(p.character is None for p in g.players.values()) else None
    )
    set_auto(client, host, True)
    clock["now"] += 2000
    tick(client)
    assert state(client, host).json()["페이즈"]["위치"] == 1            # 조건이 맞지 않으면 계속 기다린다
    for who, slot in zip([host, *others], slots(client, host)):
        confirm_pick(client, who, slot)
    tick(client)
    assert state(client, host).json()["페이즈"]["위치"] == 2            # 조건이 맞으면 넘어간다
    clock["now"] += 2000
    tick(client)
    assert state(client, host).json()["페이즈"]["위치"] == 2            # 마지막 단계에서는 넘어가지 않는다


def test_auto_advance_ignores_unlimited_phase_and_ended_game(client, make_account, make_game_work, clock):
    host, _, room, _ = started(client, make_account, make_game_work)
    set_auto(client, host, True)
    end_now(client, room["번호"])
    clock["now"] += 99999
    tick(client)
    assert state(client, host).json()["페이즈"]["위치"] == 1            # 끝난 게임은 넘기지 않는다
