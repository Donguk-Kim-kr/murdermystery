"""방 API: 만들기, 입장, 대기실, 나가기, 자동 종료 (DB_RULES B37·B38)."""
import re
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

import app.rooms as rooms_module
from app.main import sweep_rooms

CODE_RE = re.compile(r"^[A-HJ-NP-Z2-9]{6}$")


@pytest.fixture
def clock(client):
    """대기실 시계를 수동으로 흘려 보낸다."""
    reg = client.app.state.rooms
    original = reg.clock
    state = {"now": 5000.0}
    reg.clock = lambda: state["now"]
    yield state
    reg.clock = original


@pytest.fixture
def db(test_dbname):
    with psycopg.connect(f"dbname={test_dbname}", autocommit=True) as conn:
        yield conn


@pytest.fixture
def make_work(client, confirm):
    """확정 버전이 있는 작품. players 는 NPC 가 아닌 인물 수(= 최대인원)."""

    def make(owner, players=3, confirmed=True):
        wid = client.post("/api/works", headers=owner.headers, json={"제목": "저택의 비밀", "시놉시스": "폭풍우"}).json()["번호"]
        for i in range(players):
            client.post(f"/api/works/{wid}/characters", headers=owner.headers, json={"이름": f"p{i}"})
        if confirmed:
            confirm(wid)
        return wid

    return make


def create(client, who, wid, **kw):
    return client.post("/api/rooms", headers=who.headers, json={"작품_번호": wid, **kw})


def join(client, who, code):
    return client.post("/api/rooms/join", headers=who.headers, json={"입장코드": code})


def mine(client, who):
    return client.get("/api/rooms/me", headers=who.headers).json()


# ---- 만들기 ---------------------------------------------------------------------------

def test_create_room_for_own_work(client, make_account, make_work, db):
    host = make_account()
    wid = make_work(host)
    res = create(client, host, wid)
    assert res.status_code == 201
    room = res.json()
    assert CODE_RE.match(room["입장코드"]) and room["상태"] == "대기" and room["버전"] == "1.0"
    assert room["내가_방장"] is True and room["작품"]["제목"] == "저택의 비밀" and room["작품"]["최대인원"] == 3
    assert [(m["계정_번호"], m["방장"], m["플레이"]) for m in room["참가자"]] == [(host.number, True, True)]
    stored = db.execute('SELECT "작품_번호", "버전_버전", "상태" FROM "방" WHERE "번호" = %s', (room["번호"],)).fetchone()
    assert stored == (wid, "1.0", "대기")


def test_room_uses_the_latest_confirmed_version_not_string_order(client, make_account, make_work, confirm):
    host = make_account()
    wid = make_work(host)
    confirm(wid, "1.9")
    confirm(wid, "1.10")  # 문자열로 비교하면 1.9 가 더 크다. 가장 나중에 확정한 것을 써야 한다.
    assert create(client, host, wid).json()["버전"] == "1.10"


def test_version_is_fixed_when_the_room_is_created(client, make_account, make_work, confirm):
    host = make_account()
    wid = make_work(host)
    create(client, host, wid)
    confirm(wid, "2.0")  # 대기 중에 새 버전을 확정해도 이미 만든 방은 그대로다
    assert mine(client, host)["버전"] == "1.0"


def test_cannot_create_room_without_confirmed_version(client, make_account, make_work):
    host = make_account()
    res = create(client, host, make_work(host, confirmed=False))
    assert res.status_code == 409 and "확정된 버전" in res.json()["detail"]


def test_unknown_work_is_404(client, make_account):
    assert create(client, make_account(), 999999).status_code == 404


def test_host_may_choose_not_to_play(client, make_account, make_work):
    host = make_account()
    room = create(client, host, make_work(host), 방장_참여=False).json()
    assert room["참가자"][0]["플레이"] is False and room["플레이어_수"] == 0


# ---- 누가 어떤 작품으로 방을 만들 수 있나 ----------------------------------------------------

def test_private_work_room_only_for_owner_and_testers(client, make_account, make_work):
    owner, tester, stranger = make_account(), make_account(), make_account()
    wid = make_work(owner)
    client.post(f"/api/works/{wid}/testers", headers=owner.headers, json={"아이디": tester.login_id})
    assert create(client, stranger, wid).status_code == 404       # 비공개 작품이 있다는 것도 알리지 않는다
    assert create(client, tester, wid).status_code == 201         # 테스터(비공개 플레이)
    assert create(client, owner, wid).status_code == 201          # 제작자 본인


def test_owner_can_create_private_room(client, make_account, make_work):
    owner = make_account()
    assert create(client, owner, make_work(owner)).status_code == 201


def test_public_work_room_for_anyone(client, make_account, make_work):
    owner, other = make_account(), make_account()
    wid = make_work(owner)
    client.post(f"/api/works/{wid}/publish", headers=owner.headers)
    assert create(client, other, wid).status_code == 201


def test_staff_locked_work_room_is_closed_until_returned_to_owner(client, make_account, make_work):
    owner, tester, admin = make_account(), make_account(), make_account("관리자")
    wid = make_work(owner)
    client.post(f"/api/works/{wid}/testers", headers=owner.headers, json={"아이디": tester.login_id})
    client.post(f"/api/works/{wid}/publish", headers=owner.headers)
    client.post(f"/api/works/{wid}/unpublish", headers=admin.headers)      # 관리자가 비공개
    for who in (owner, tester):
        res = create(client, who, wid)
        assert res.status_code == 403 and "방을 만들 수 없습니다" in res.json()["detail"]
    client.post(f"/api/works/{wid}/return-to-owner", headers=admin.headers)
    assert create(client, owner, wid).status_code == 201


def test_admin_cannot_host_someone_elses_private_work(client, make_account, make_work):
    owner, admin = make_account(), make_account("관리자")
    assert create(client, admin, make_work(owner)).status_code == 404


# ---- 입장 -----------------------------------------------------------------------------

def test_join_by_code_is_case_insensitive_and_tolerates_spaces(client, make_account, make_work):
    host, guest = make_account(), make_account()
    code = create(client, host, make_work(host)).json()["입장코드"]
    res = join(client, guest, f"  {code.lower()} ")
    assert res.status_code == 200
    room = res.json()
    assert [m["계정_번호"] for m in room["참가자"]] == [host.number, guest.number]
    assert room["내가_방장"] is False and room["플레이어_수"] == 2
    assert {m["계정_번호"] for m in mine(client, host)["참가자"]} == {host.number, guest.number}


def test_join_does_not_depend_on_work_visibility(client, make_account, make_work):
    host, guest = make_account(), make_account()
    code = create(client, host, make_work(host)).json()["입장코드"]   # 비공개 작품
    assert join(client, guest, code).status_code == 200


def test_wrong_code_is_404_and_repeated_failures_are_rate_limited(client, make_account, make_work):
    host, guest = make_account(), make_account()
    code = create(client, host, make_work(host)).json()["입장코드"]
    for _ in range(5):
        assert join(client, guest, "ZZZZZZ").status_code == 404
    assert join(client, guest, code).status_code == 429            # 맞는 코드여도 잠시 막힌다


def test_successful_join_resets_failure_count(client, make_account, make_work):
    host, guest = make_account(), make_account()
    code = create(client, host, make_work(host)).json()["입장코드"]
    for _ in range(4):
        join(client, guest, "ZZZZZZ")
    assert join(client, guest, code).status_code == 200
    client.post("/api/rooms/leave", headers=guest.headers)
    for _ in range(4):
        assert join(client, guest, "ZZZZZZ").status_code == 404   # 다시 처음부터 센다


def test_room_capacity_counts_players_only(client, make_account, make_work):
    host, a, b = make_account(), make_account(), make_account()
    code = create(client, host, make_work(host, players=2)).json()["입장코드"]   # 최대 2명, 방장도 플레이
    assert join(client, a, code).status_code == 200
    res = join(client, b, code)
    assert res.status_code == 409 and "가득" in res.json()["detail"]


def test_observer_host_leaves_room_for_one_more_player(client, make_account, make_work):
    host, a, b = make_account(), make_account(), make_account()
    code = create(client, host, make_work(host, players=2), 방장_참여=False).json()["입장코드"]
    assert join(client, a, code).status_code == 200
    assert join(client, b, code).status_code == 200


# ---- 한 번에 한 방 ---------------------------------------------------------------------

def test_one_room_at_a_time_for_hosts_and_guests(client, make_account, make_work):
    host, other_host, guest = make_account(), make_account(), make_account()
    wid = make_work(host)
    code = create(client, host, wid).json()["입장코드"]
    assert create(client, host, wid).status_code == 409             # 방장은 두 번째 방을 만들 수 없다
    other_code = create(client, other_host, make_work(other_host)).json()["입장코드"]
    assert join(client, guest, code).status_code == 200
    assert join(client, guest, other_code).status_code == 409       # 입장자는 다른 방에 들어갈 수 없다
    assert create(client, guest, make_work(guest)).status_code == 409
    client.post("/api/rooms/leave", headers=guest.headers)
    assert join(client, guest, other_code).status_code == 200       # 나가면 가능


def test_concurrent_create_makes_only_one_room(client, make_account, make_work):
    host = make_account()
    wid = make_work(host)
    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = sorted(r.status_code for r in pool.map(lambda _: create(client, host, wid), range(4)))
    assert codes == [201, 409, 409, 409]


def test_room_code_collision_is_retried(client, make_account, make_work, monkeypatch):
    a, b = make_account(), make_account()
    seq = iter(["QWERTY", "QWERTY", "ASDFGH"])
    monkeypatch.setattr(rooms_module, "new_code", lambda: next(seq))
    assert create(client, a, make_work(a)).json()["입장코드"] == "QWERTY"
    assert create(client, b, make_work(b)).json()["입장코드"] == "ASDFGH"    # 겹친 코드는 건너뛴다


# ---- 방장이 정하는 입장코드 ---------------------------------------------------------------------

def test_host_chooses_the_entry_code_and_it_is_normalized_to_upper_case(client, make_account, make_work):
    host, guest = make_account(), make_account()
    made = create(client, host, make_work(host), 입장코드="  우리방2024 ")
    assert made.status_code == 201 and made.json()["입장코드"] == "우리방2024"
    other = create(client, make_account(), make_work(host), 입장코드="abcd")             # 남의 작품은 비공개라 실패해도 코드 검사가 먼저 걸린다
    assert other.status_code in (201, 403, 404)
    assert join(client, guest, "우리방2024").status_code == 200
    host2 = make_account()
    lower = create(client, host2, make_work(host2), 입장코드="friends7")
    assert lower.status_code == 201 and lower.json()["입장코드"] == "FRIENDS7"
    assert join(client, make_account(), "friends7").status_code == 200                   # 입력은 대소문자를 가리지 않는다


@pytest.mark.parametrize("code, ok", [("ABC", False), ("ABCD", True), ("A" * 10, True), ("A" * 11, False), ("AB CD", False), ("AB-CD", False), ("AB!D", False), ("한글방", False), ("한글방1", True)])
def test_entry_code_length_and_characters(client, make_account, make_work, code, ok):
    host = make_account()
    res = create(client, host, make_work(host), 입장코드=code)
    assert (res.status_code == 201) is ok
    if not ok:
        assert res.status_code == 422


def test_blank_entry_code_means_automatic(client, make_account, make_work):
    host = make_account()
    res = create(client, host, make_work(host), 입장코드="   ")
    assert res.status_code == 201 and CODE_RE.match(res.json()["입장코드"])


def test_an_entry_code_in_use_by_an_open_room_is_refused(client, make_account, make_work):
    a, b = make_account(), make_account()
    assert create(client, a, make_work(a), 입장코드="SAMECODE").status_code == 201
    dup = create(client, b, make_work(b), 입장코드="samecode")
    assert dup.status_code == 409 and "이미 사용 중인 입장코드" in dup.json()["detail"]
    assert mine(client, b) is None                                                        # 거절되면 방이 만들어지지 않는다


def test_an_entry_code_can_be_reused_after_the_room_is_closed(client, make_account, make_work, db):
    a, b, guest = make_account(), make_account(), make_account()
    first = create(client, a, make_work(a), 입장코드="REUSE01").json()
    assert client.post("/api/rooms/leave", headers=a.headers).status_code == 204            # 방장이 나가 방이 닫힌다
    assert join(client, guest, "REUSE01").status_code == 404                                 # 닫힌 방의 코드로는 들어갈 수 없다
    second = create(client, b, make_work(b), 입장코드="REUSE01")
    assert second.status_code == 201 and second.json()["번호"] != first["번호"]
    assert join(client, guest, "REUSE01").status_code == 200                                 # 새 방으로 들어간다
    assert mine(client, guest)["번호"] == second.json()["번호"]
    rows = db.execute('SELECT 상태 FROM "방" WHERE 입장코드 = %s ORDER BY 번호', ("REUSE01",)).fetchall()
    assert [r[0] for r in rows] == ["종료", "대기"]


# ---- 대기실 상태·나가기·닫기 -------------------------------------------------------------

def test_my_room_is_null_when_not_in_a_room(client, make_account):
    assert mine(client, make_account()) is None


def test_member_leaves_and_host_closes_the_room(client, make_account, make_work, db):
    host, guest = make_account(), make_account()
    room = create(client, host, make_work(host)).json()
    join(client, guest, room["입장코드"])
    assert client.post("/api/rooms/leave", headers=guest.headers).status_code == 204
    assert [m["계정_번호"] for m in mine(client, host)["참가자"]] == [host.number]
    join(client, guest, room["입장코드"])
    assert client.post("/api/rooms/leave", headers=host.headers).status_code == 204      # 방장이 나가면 방이 닫힌다
    assert mine(client, host) is None and mine(client, guest) is None
    state, ended = db.execute('SELECT "상태", "종료일시" IS NOT NULL FROM "방" WHERE "번호" = %s', (room["번호"],)).fetchone()
    assert (state, ended) == ("종료", True)
    assert join(client, guest, room["입장코드"]).status_code == 404           # 닫힌 방의 코드는 더 이상 방을 가리키지 않는다(다른 방이 다시 쓸 수 있다)
    assert client.post("/api/rooms/leave", headers=host.headers).status_code == 404


def test_everyone_moves_self_and_only_host_moves_others(client, make_account, make_work):
    host, guest = make_account(), make_account()
    code = create(client, host, make_work(host, players=2)).json()["입장코드"]
    join(client, guest, code)
    patch = lambda who, **body: client.patch("/api/rooms/me", headers=who.headers, json=body)
    res = patch(host, 플레이=False)
    assert res.status_code == 200 and res.json()["플레이어_수"] == 1
    res = patch(guest, 플레이=False)                                      # 참가자도 자기 자리는 옮길 수 있다
    assert res.status_code == 200 and res.json()["플레이어_수"] == 0
    assert patch(guest, 플레이=True, 계정_번호=host.number).status_code == 403   # 남은 방장만
    res = patch(host, 플레이=True, 계정_번호=guest.number)                # 방장이 참가자를 옮긴다
    assert res.status_code == 200 and res.json()["플레이어_수"] == 1
    assert patch(host, 플레이=True, 계정_번호=999999999).status_code == 404
    assert patch(make_account(), 플레이=True).status_code == 404


def test_gm_observe_choice_is_own_only(client, make_account, make_work):
    host, guest = make_account(), make_account()
    code = create(client, host, make_work(host, players=2)).json()["입장코드"]
    join(client, guest, code)
    patch = lambda who, **body: client.patch("/api/rooms/me", headers=who.headers, json=body)
    res = patch(guest, 플레이=False, GM관전=True)
    assert res.status_code == 200
    me = [m for m in res.json()["참가자"] if m["계정_번호"] == guest.number][0]
    assert me["플레이"] is False and me["GM관전"] is True
    assert patch(host, GM관전=True, 계정_번호=guest.number).status_code == 403


def test_host_cannot_rejoin_as_player_when_room_is_full(client, make_account, make_work):
    host, a, b = make_account(), make_account(), make_account()
    code = create(client, host, make_work(host, players=2), 방장_참여=False).json()["입장코드"]
    join(client, a, code)
    join(client, b, code)
    assert client.patch("/api/rooms/me", headers=host.headers, json={"플레이": True}).status_code == 409


def test_guest_who_stops_polling_leaves_the_waiting_room(client, make_account, make_work, clock):
    host, guest, other = make_account(), make_account(), make_account()
    code = create(client, host, make_work(host)).json()["입장코드"]
    other_code = create(client, other, make_work(other)).json()["입장코드"]
    join(client, guest, code)
    clock["now"] += 10
    assert mine(client, guest) is not None                       # 폴링이 계속되는 동안은 유지된다
    clock["now"] += 30
    assert mine(client, guest) is not None                       # 직전 폴링(10초 전) 이후 30초라 아직 유지
    clock["now"] += 50                                           # 50초 동안 폴링이 없었다(제한 45초)
    assert [m["계정_번호"] for m in mine(client, host)["참가자"]] == [host.number]
    assert join(client, guest, other_code).status_code == 200    # 자리가 풀려 다른 방에 들어갈 수 있다


def test_host_stays_even_if_polling_stops(client, make_account, make_work, clock):
    host = make_account()
    create(client, host, make_work(host))
    clock["now"] += 3600
    assert mine(client, host) is not None


def test_host_room_is_restored_after_server_restart_but_guests_are_lost(client, make_account, make_work):
    host, guest = make_account(), make_account()
    room = create(client, host, make_work(host)).json()
    join(client, guest, room["입장코드"])
    client.app.state.rooms.remove_room(room["번호"])                # 서버 재시작과 같은 효과(메모리만 사라짐)
    assert mine(client, guest) is None
    assert join(client, guest, room["입장코드"]).status_code == 409   # 방장이 돌아오기 전에는 입장할 수 없다
    restored = mine(client, host)
    assert restored["번호"] == room["번호"] and [m["계정_번호"] for m in restored["참가자"]] == [host.number]
    assert join(client, guest, room["입장코드"]).status_code == 200   # 방장이 돌아온 뒤에는 다시 입장한다


# ---- 자동 종료 ---------------------------------------------------------------------------

def test_waiting_room_expires_after_six_hours(client, make_account, make_work, db):
    host, guest = make_account(), make_account()
    room = create(client, host, make_work(host)).json()
    db.execute('UPDATE "방" SET "상태변경일시" = CURRENT_TIMESTAMP - interval \'7 hours\' WHERE "번호" = %s', (room["번호"],))
    assert join(client, guest, room["입장코드"]).status_code == 404       # 만료된 방은 종료되어 코드가 더 이상 방을 가리키지 않는다
    assert db.execute('SELECT "상태" FROM "방" WHERE "번호" = %s', (room["번호"],)).fetchone()[0] == "종료"
    assert mine(client, host) is None


def test_waiting_room_younger_than_six_hours_stays(client, make_account, make_work, db):
    host, guest = make_account(), make_account()
    room = create(client, host, make_work(host)).json()
    db.execute('UPDATE "방" SET "상태변경일시" = CURRENT_TIMESTAMP - interval \'5 hours\' WHERE "번호" = %s', (room["번호"],))
    assert join(client, guest, room["입장코드"]).status_code == 200


def test_sweep_closes_expired_rooms_and_clears_memory(client, make_account, make_work, db):
    host = make_account()
    room = create(client, host, make_work(host)).json()
    db.execute('UPDATE "방" SET "상태변경일시" = CURRENT_TIMESTAMP - interval \'7 hours\' WHERE "번호" = %s', (room["번호"],))
    sweep_rooms(client.app)
    assert client.app.state.rooms.get(room["번호"]) is None
    assert db.execute('SELECT "상태" FROM "방" WHERE "번호" = %s', (room["번호"],)).fetchone()[0] == "종료"


def test_sweep_clears_memory_of_rooms_closed_in_the_database(client, make_account, make_work, db):
    host = make_account()
    room = create(client, host, make_work(host)).json()
    db.execute('UPDATE "방" SET "상태" = \'종료\' WHERE "번호" = %s', (room["번호"],))
    sweep_rooms(client.app)
    assert client.app.state.rooms.get(room["번호"]) is None


# ---- 로그인 필요 -------------------------------------------------------------------------

@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/rooms", {"작품_번호": 1}), ("post", "/api/rooms/join", {"입장코드": "ABC234"}),
    ("get", "/api/rooms/me", None), ("patch", "/api/rooms/me", {"플레이": True}), ("post", "/api/rooms/leave", None),
])
def test_requires_login(client, method, path, body):
    assert getattr(client, method)(path, **({"json": body} if body is not None else {})).status_code == 401
