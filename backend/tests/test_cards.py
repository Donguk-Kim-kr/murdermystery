"""카드 스크립트가 게임에서 실행되는 것 (docs/ENGINE_SPEC.md): 프롤로그 → 캐릭터 선택 → 프로필 숙지."""
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app import narrative
from app.default_phases import PROLOGUE, CHARACTER_SELECT, PROFILE, INTRO
from app.narrative import Part

from test_game import advance, create_room, join, start, state


@pytest.fixture
def db(test_dbname):
    with psycopg.connect(f"dbname={test_dbname}", autocommit=True) as conn:
        yield conn


@pytest.fixture
def make_scripted_game(client, make_account, db):
    """카드(이름, 스크립트, 설정)를 페이즈 하나에 하나씩 놓은 확정 작품으로 방을 열어 게임을 시작한다."""

    def make(cards, players=3, observer_host=False, story="모두가 읽는 공통 스토리", unchecked=(), setup=None, edit=None, characters=None, start_status=200):
        """`unchecked` 에 든 카드 이름의 스크립트는 확정(검사)을 통과한 뒤 스냅샷에서 바꿔 넣는다(검사를 통과하지 못할 스크립트를 실행해 보려고)."""
        host = make_account()
        wid = client.post("/api/works", headers=host.headers, json={"제목": "스크립트 시험", "공통스토리": story}).json()["번호"]
        for i in range(characters if characters is not None else players):
            raw = narrative.join([Part(None, f"{i}번의 서사 하나"), Part(None, f"{i}번의 서사 둘")])
            res = client.post(f"/api/works/{wid}/characters", headers=host.headers, json={
                "이름": f"인물{i}", "직업": "의사", "서사": raw, "비밀": f"비밀{i}",
                **({"소개": "안녕하세요, 저는 의사입니다."} if i == 0 else {}),         # 소개가 있는 인물과 없는 인물
            })
            assert res.status_code == 201, res.text
        if setup:
            setup(client, host, wid)
        swaps = {}
        libs = {}                                                                   # 같은 이름의 카드를 여러 번 놓으면 같은 진행단계를 가리킨다
        for position, (name, script, settings) in enumerate(cards, 1):
            if name in unchecked:
                swaps[f"{name}-{wid}"], script = script, ""
            if name not in libs:
                libs[name] = client.post("/api/library/phases", headers=host.headers, json={
                    "이름": f"{name}-{wid}", "설명": name, "규칙": {"스크립트": script} if script else {},
                })
                assert libs[name].status_code == 201, libs[name].text
            lib = libs[name]
            made = client.post(f"/api/works/{wid}/phases/insert", headers=host.headers, json={"position": position})
            assert made.status_code == 201, made.text
            slot = made.json()["phases"][position - 1]["순서"]
            placed = client.post(f"/api/works/{wid}/content/phase-steps", headers=host.headers, json={
                "진행순서_순서": slot, "진행단계_번호": lib.json()["번호"], **({"설정": settings} if settings else {}),
            })
            assert placed.status_code == 201, placed.text
        assert client.post(f"/api/works/{wid}/confirm", headers=host.headers, json={}).status_code == 201
        if swaps or edit:
            scenario = db.execute('SELECT "시나리오" FROM "버전" WHERE "작품_번호" = %s', (wid,)).fetchone()[0]
            for item in scenario["라이브러리"]["진행단계"]:
                if item["이름"] in swaps:
                    item["규칙"] = {"스크립트": swaps[item["이름"]]}
            if edit:
                edit(scenario)                                              # 확정 검사를 통과하지 못할 내용을 스냅샷에 직접 넣는다(시험 전용)
            db.execute('ALTER TABLE "버전" DISABLE TRIGGER USER')          # 확정된 버전은 바꿀 수 없게 막혀 있어 잠시 푼다(시험 전용)
            db.execute('UPDATE "버전" SET "시나리오" = %s WHERE "작품_번호" = %s', (Jsonb(scenario), wid))
            db.execute('ALTER TABLE "버전" ENABLE TRIGGER USER')
        room = create_room(client, host, wid, **({"방장_참여": False} if observer_host else {}))
        others = [make_account() for _ in range(players - (0 if observer_host else 1))]
        for o in others:
            join(client, o, room["입장코드"])
        res = start(client, host)
        assert res.status_code == start_status, res.text
        return host, others, room, wid

    return make


def answer(client, who, qid, value=True):
    return client.post("/api/game/me/answer", headers=who.headers, json={"질문ID": qid, "값": value})


def block(view, name):
    return next((b for b in view["화면"] if b["이름"] == name), None)


def tab(view, name):
    return next((t for t in view["탭"] if t["이름"] == name), None)


def players_of(host, others):
    return [host, *others]


def pick(client, who, slot):
    """캐릭터 선택 화면에서 인물을 클릭하고 확인한다."""
    view = state(client, who).json()
    return answer(client, who, block(view, "캐릭터 선택")["질문ID"], slot)


def all_pick(client, people):
    slots = [c["값"] for c in block(state(client, people[0]).json(), "캐릭터 선택")["항목"]]
    for who, slot in zip(people, slots):
        assert pick(client, who, slot).status_code == 200


# ---- 프롤로그 ----------------------------------------------------------------------------------

def test_prologue_shows_story_tab_and_read_confirmation(client, make_scripted_game):
    host, others, _, _ = make_scripted_game([("프롤로그", PROLOGUE, None)])
    view = state(client, others[0]).json()
    read = block(view, "공통 스토리")
    assert read["종류"] == "읽기" and read["내용"] == "모두가 읽는 공통 스토리"
    assert read["확인필요"] is True and read["확인함"] is False and read["현황"] == {"완료": 0, "전체": 3}
    assert tab(view, "공통 스토리")["내용"] == "모두가 읽는 공통 스토리"


def test_confirming_read_updates_progress_for_everyone_once(client, make_scripted_game):
    host, others, _, _ = make_scripted_game([("프롤로그", PROLOGUE, None)])
    qid = block(state(client, host).json(), "공통 스토리")["질문ID"]
    v = state(client, host).json()["상태_버전"]
    res = answer(client, others[0], qid)
    assert res.status_code == 200
    mine = block(res.json(), "공통 스토리")
    assert mine["확인함"] is True and mine["확인필요"] is False and mine["현황"] == {"완료": 1, "전체": 3}
    assert res.json()["상태_버전"] == v + 1
    assert block(state(client, host).json(), "공통 스토리")["현황"] == {"완료": 1, "전체": 3}
    again = answer(client, others[0], qid)                                # 두 번 눌러도 한 번으로 센다
    assert again.status_code == 200 and again.json()["상태_버전"] == v + 1
    for who in (host, others[1]):
        answer(client, who, qid)
    assert block(state(client, host).json(), "공통 스토리")["현황"] == {"완료": 3, "전체": 3}
    assert state(client, host).json()["페이즈"]["위치"] == 1              # 전원 확인해도 저절로 넘어가지 않는다


def test_observer_sees_story_and_progress_but_cannot_confirm(client, make_scripted_game):
    host, others, _, _ = make_scripted_game([("프롤로그", PROLOGUE, None)], players=2, observer_host=True)
    view = state(client, host).json()
    read = block(view, "공통 스토리")
    assert read["내용"] == "모두가 읽는 공통 스토리" and read["확인필요"] is False and read["현황"]["전체"] == 2
    assert answer(client, host, read["질문ID"]).status_code == 403


def test_story_tab_stays_by_default_and_can_be_dropped_by_setting(client, make_scripted_game):
    host, others, _, _ = make_scripted_game([("프롤로그", PROLOGUE, None), ("빈", "", None)])
    assert advance(client, host).status_code == 200
    assert tab(state(client, others[0]).json(), "공통 스토리") is not None          # 내용 유지(기본)

    host, others, _, _ = make_scripted_game([("프롤로그", PROLOGUE, {"내용유지": False}), ("빈", "", None)])
    assert tab(state(client, host).json(), "공통 스토리") is not None             # 그 단계에서는 보인다
    assert advance(client, host).status_code == 200
    assert tab(state(client, host).json(), "공통 스토리") is None                 # 다음 단계에서는 사라진다


# ---- 캐릭터 선택 ---------------------------------------------------------------------------------

def two_phase_game(make_scripted_game, **kw):
    return make_scripted_game([("캐릭터 선택", CHARACTER_SELECT, None), ("프로필 숙지", PROFILE, None)], **kw)


def test_character_select_shows_choices_and_progress(client, make_scripted_game):
    host, others, _, _ = two_phase_game(make_scripted_game)
    view = state(client, others[0]).json()
    choice = block(view, "캐릭터 선택")
    assert choice["종류"] == "선택지" and choice["확인필요"] is True and choice["내_선택_끝남"] is False
    assert [i["이름"] for i in choice["항목"]] == ["인물0", "인물1", "인물2"]
    assert all(i["직업"] == "의사" and i["선택한_계정"] is None for i in choice["항목"])
    assert "비밀" not in str(choice) and "서사" not in str(choice)
    assert block(view, "선택 완료")["완료"] == 0 and block(view, "선택 완료")["전체"] == 3


def test_confirming_a_character_assigns_it_first_come_first_served(client, make_scripted_game, db):
    host, others, room, _ = two_phase_game(make_scripted_game)
    slots = [i["값"] for i in block(state(client, host).json(), "캐릭터 선택")["항목"]]
    res = pick(client, others[0], slots[0])
    assert res.status_code == 200
    body = res.json()
    assert body["나"]["인물_순서"] == slots[0] and block(body, "선택 완료")["완료"] == 1
    assert block(body, "캐릭터 선택")["내_선택_끝남"] is True
    saved = db.execute('SELECT "인물_순서" FROM "참여" WHERE "계정_번호" = %s AND "진행_번호" = (SELECT "번호" FROM "진행" WHERE "방_번호" = %s)',
                       (others[0].number, room["번호"])).fetchone()[0]
    assert saved == slots[0]
    late = pick(client, others[1], slots[0])                                 # 같은 인물을 나중에 확인
    assert late.status_code == 200
    seen = late.json()
    assert seen["나"]["인물_순서"] is None
    assert [n["글"] for n in seen["알림"]] == ["이미 다른 사람이 고른 인물입니다"]
    assert block(seen, "캐릭터 선택")["항목"][0]["선택한_계정"] == others[0].number
    assert pick(client, others[1], slots[1]).json()["나"]["인물_순서"] == slots[1]   # 다른 인물은 고를 수 있다


def test_concurrent_confirms_for_one_character_assign_exactly_one(client, make_scripted_game, db):
    host, others, room, _ = two_phase_game(make_scripted_game)
    people = [host, *others]
    slot = block(state(client, host).json(), "캐릭터 선택")["항목"][0]["값"]
    qid = block(state(client, host).json(), "캐릭터 선택")["질문ID"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        codes = list(pool.map(lambda w: answer(client, w, qid, slot).status_code, people))
    assert codes == [200, 200, 200]                                           # 요청은 모두 받아들여지고
    owners = db.execute('SELECT count(*) FROM "참여" WHERE "인물_순서" = %s AND "진행_번호" = (SELECT "번호" FROM "진행" WHERE "방_번호" = %s)',
                        (slot, room["번호"])).fetchone()[0]
    assert owners == 1                                                         # 인물은 한 사람만 갖는다
    assert sum(1 for w in people if state(client, w).json()["나"]["인물_순서"] == slot) == 1


def test_advance_is_blocked_until_everyone_has_a_character(client, make_scripted_game):
    host, others, _, _ = two_phase_game(make_scripted_game)
    res = advance(client, host)
    assert res.status_code == 409 and res.json()["detail"] == "캐릭터 선택이 완료되지 않았습니다."
    slots = [i["값"] for i in block(state(client, host).json(), "캐릭터 선택")["항목"]]
    pick(client, host, slots[0])
    pick(client, others[0], slots[1])
    assert advance(client, host).status_code == 409                          # 한 명이 남았다
    pick(client, others[1], slots[2])
    assert advance(client, host).status_code == 200
    assert state(client, host).json()["페이즈"]["위치"] == 2


def test_time_up_does_not_skip_character_select_even_with_auto_advance(client, make_scripted_game):
    from app.main import tick_games

    host, others, room, _ = two_phase_game(make_scripted_game)
    reg = client.app.state.games
    original = reg.clock
    t = {"now": 1000.0}
    reg.clock = lambda: t["now"]
    try:
        client.post("/api/game/me/settings", headers=host.headers, json={"자동_진행": True})
        t["now"] += 99999
        tick_games(client.app)
        assert state(client, host).json()["페이즈"]["위치"] == 1
    finally:
        reg.clock = original


def test_stale_and_unknown_questions_are_rejected_without_changing_the_version(client, make_scripted_game):
    host, others, _, _ = two_phase_game(make_scripted_game)
    qid = block(state(client, host).json(), "캐릭터 선택")["질문ID"]
    v = state(client, host).json()["상태_버전"]
    assert answer(client, host, "없는:질문", 1).status_code == 409
    assert answer(client, host, qid + "x", 1).status_code == 409
    assert answer(client, host, qid, {"a": "x" * 5000}).status_code == 422
    assert state(client, host).json()["상태_버전"] == v
    all_pick(client, [host, *others])
    assert advance(client, host).status_code == 200
    assert answer(client, host, qid, 1).status_code == 409                    # 이전 단계의 질문


def test_only_players_can_answer(client, make_scripted_game):
    host, others, _, _ = two_phase_game(make_scripted_game, players=2, observer_host=True)
    qid = block(state(client, host).json(), "캐릭터 선택")["질문ID"]
    assert answer(client, host, qid, 1).status_code == 403


# ---- 프로필 숙지 ---------------------------------------------------------------------------------

def test_profile_shows_only_my_own_narrative(client, make_scripted_game):
    host, others, _, _ = two_phase_game(make_scripted_game)
    people = [host, *others]
    all_pick(client, people)
    assert advance(client, host).status_code == 200
    mine = {}
    for who in people:
        view = state(client, who).json()
        t = tab(view, "개인 서사")
        read = block(view, "개인 서사")
        assert t is not None and read is not None
        assert t["내용"] == read["내용"] and read["확인필요"] is True
        assert read["현황"] == {"완료": 0, "전체": 3}
        mine[who.number] = (view["나"]["인물_순서"], read["내용"])
    slots = sorted(v[0] for v in mine.values())
    index_of = {slot: i for i, slot in enumerate(slots)}
    for who in people:
        slot, text = mine[who.number]
        n = index_of[slot]
        assert text == f"▶ 서사\n{n}번의 서사 하나\n\n{n}번의 서사 둘\n\n▶ 비밀\n비밀{n}"   # 따로 고르지 않으면 서사 전체와 비밀이 보인다, 자기 인물의 것만
        others_text = [v[1] for k, v in mine.items() if k != who.number]
        assert not any(o in state(client, who).text for o in others_text)        # 다른 사람의 서사는 응답 어디에도 없다


def test_profile_card_setting_chooses_parts_per_character(client, make_scripted_game):
    # 설정의 키는 인물의 순서(문자열)이다. 시작 전에는 순서를 모르므로 작품을 만든 뒤 알아내 쓰는 대신, 모든 인물이 같은 서사를 받는 기본값과 비교한다.
    host, others, _, wid = two_phase_game(make_scripted_game)
    people = [host, *others]
    all_pick(client, people)
    game = client.app.state.games.of_account(host.number)
    slots = [c["순서"] for c in game.characters]
    # 카드 설정을 바꾼 새 게임을 만들 수 없으므로, 실행 중 카드의 설정만 바꿔서 다음 단계를 시험한다.
    row = next(r for r in game.snapshot["진행구성"] if r["진행순서_순서"] == game.phases[1]["순서"])
    row["설정"] = {"개인서사공개": {str(slots[0]): [1, 2], str(slots[1]): [2]}}
    assert advance(client, host).status_code == 200
    texts = {}
    for who in people:
        v = state(client, who).json()
        texts[v["나"]["인물_순서"]] = block(v, "개인 서사")["내용"]
    names = {s: i for i, s in enumerate(slots)}
    section = lambda s, body: f"▶ 서사\n{body}\n\n▶ 비밀\n비밀{names[s]}"
    assert texts[slots[0]] == section(slots[0], f"{names[slots[0]]}번의 서사 하나\n\n{names[slots[0]]}번의 서사 둘")
    assert texts[slots[1]] == section(slots[1], f"{names[slots[1]]}번의 서사 둘")
    assert texts[slots[2]] == section(slots[2], f"{names[slots[2]]}번의 서사 하나\n\n{names[slots[2]]}번의 서사 둘")      # 고르지 않은 인물은 전체


def test_profile_read_progress_counts_across_players(client, make_scripted_game):
    host, others, _, _ = two_phase_game(make_scripted_game)
    people = [host, *others]
    all_pick(client, people)
    advance(client, host)
    qid = block(state(client, host).json(), "개인 서사")["질문ID"]
    answer(client, others[0], qid)
    answer(client, others[1], qid)
    for who in people:
        assert block(state(client, who).json(), "개인 서사")["현황"] == {"완료": 2, "전체": 3}


def test_observer_does_not_see_personal_narrative(client, make_scripted_game):
    host, others, _, _ = two_phase_game(make_scripted_game, players=2, observer_host=True)
    all_pick(client, others)
    assert advance(client, others[0]).status_code == 200                     # 방장이 관전이면 첫 플레이어가 진행 권한을 가진다
    view = state(client, host).json()
    assert block(view, "개인 서사") is None and tab(view, "개인 서사") is None
    assert "서사 하나" not in state(client, host).text


def test_player_without_character_gets_no_personal_screens(client, make_scripted_game):
    host, others, _, _ = two_phase_game(make_scripted_game)
    game = client.app.state.games.of_account(host.number)
    game.card_conditions.clear()                                             # 방장이 캐릭터를 다 고르기 전에 넘긴 경우를 시험한다
    slot = block(state(client, host).json(), "캐릭터 선택")["항목"][0]["값"]
    pick(client, host, slot)
    assert advance(client, host).status_code == 200
    assert block(state(client, host).json(), "개인 서사") is not None
    assert block(state(client, others[0]).json(), "개인 서사") is None       # 인물이 없는 플레이어에게는 보여 주지 않는다
    assert state(client, others[0]).json()["오류"] == []


# ---- 오류와 안전 -----------------------------------------------------------------------------------

def test_script_errors_are_reported_to_host_only_and_game_continues(client, make_scripted_game):
    host, others, _, _ = make_scripted_game([
        ("깨짐", "def 실행(카드):\n    x = 몰라()", None),
        ("끝없음", "def 실행(카드):\n    while True:\n        pass", None),
        ("런타임", "def 실행(카드):\n    x = 1 / 0", None),
        ("정상", PROLOGUE, None),
    ], unchecked={"깨짐"})
    # 한 페이즈에 카드가 하나씩이라, 같은 시험을 페이즈마다 확인한다
    assert "스크립트 오류" in state(client, host).json()["오류"][0]["메시지"]
    assert "알 수 없는 이름" in state(client, host).json()["오류"][0]["메시지"]
    assert state(client, others[0]).json()["오류"] == []
    advance(client, host)
    assert "너무 오래" in state(client, host).json()["오류"][0]["메시지"]
    advance(client, host)
    assert "실행 중 오류" in state(client, host).json()["오류"][0]["메시지"]
    advance(client, host)
    assert state(client, host).json()["오류"] == [] and block(state(client, host).json(), "공통 스토리") is not None


def test_script_cannot_do_things_it_is_not_given(client, make_scripted_game):
    host, _, _, _ = make_scripted_game([("나쁨", "import os\ndef 실행(카드):\n    pass", None)], unchecked={"나쁨"})
    assert "함수(def) 밖" in state(client, host).json()["오류"][0]["메시지"]


def test_end_phase_command_moves_to_next_phase(client, make_scripted_game):
    host, _, _, _ = make_scripted_game([
        ("바로끝", "def 실행(카드):\n    모두.보이기(글('첫 화면', '첫 화면입니다'))\n    단계_끝내기()", None),
        ("다음", PROLOGUE, None),
    ])
    view = state(client, host).json()
    assert view["페이즈"]["위치"] == 2 and block(view, "공통 스토리") is not None
    assert block(view, "첫 화면") is None                                          # 이전 단계의 화면은 사라진다


def test_end_phase_command_respects_progress_conditions(client, make_scripted_game):
    host, _, _, _ = make_scripted_game([
        ("선택", CHARACTER_SELECT.replace("while 인물_없는_플레이어가_있다():", "단계_끝내기()\n    while 인물_없는_플레이어가_있다():"), None),
        ("다음", PROLOGUE, None),
    ])
    assert state(client, host).json()["페이즈"]["위치"] == 1                  # 조건이 맞지 않아 넘어가지 못했다


def test_end_game_command_ends_the_game(client, make_scripted_game, db):
    host, others, room, _ = make_scripted_game([("끝", "def 실행(카드):\n    게임_종료()\n    모두.보이기(글('전체 공개', '전체 공개입니다'))", None)])
    view = state(client, host).json()
    assert view["종료"] is True and block(view, "전체 공개") is not None
    assert db.execute('SELECT "상태" FROM "진행" WHERE "방_번호" = %s', (room["번호"],)).fetchone()[0] == "종료"


def test_screens_reset_on_each_phase_and_notices_are_private(client, make_scripted_game):
    host, others, _, _ = make_scripted_game([
        ("가", "def 실행(카드):\n    모두.보이기(글('공용 안내', '공용'))\n    플레이어들()[0].알림('첫 사람에게만')\n    플레이어들()[1].보이기(글('개인 안내', '둘째에게만'))", None),
        ("나", "def 실행(카드):\n    pass", None),
    ])
    first, second, third = host, others[0], others[1]
    assert [n["글"] for n in state(client, first).json()["알림"]] == ["첫 사람에게만"]
    assert state(client, second).json()["알림"] == [] and state(client, third).json()["알림"] == []
    assert block(state(client, second).json(), "개인 안내") is not None
    names = lambda who: sorted(b["내용"] for b in state(client, who).json()["화면"])
    assert names(first) == ["공용"] and names(second) == ["공용", "둘째에게만"] and names(third) == ["공용"]
    advance(client, host)
    assert state(client, first).json()["화면"] == []


def test_game_state_includes_no_private_character_fields_even_with_scripts(client, make_scripted_game):
    host, others, _, _ = two_phase_game(make_scripted_game)
    for who in (host, *others):
        text = state(client, who).text
        assert "비밀" not in text and "서사 하나" not in text


def test_confirmed_snapshot_carries_parsed_story_parts(client, make_scripted_game):
    host, _, _, _ = two_phase_game(make_scripted_game)
    game = client.app.state.games.of_account(host.number)
    person = game.snapshot["인물"][0]
    assert [p["본문"] for p in person["서사_부분"]] == [f"0번의 서사 하나", f"0번의 서사 둘"]
    assert all(len(p["ID"]) == 6 for p in person["서사_부분"])


# ---- 자기소개 --------------------------------------------------------------------------------

def test_intro_shows_only_the_intro_lines_of_characters_that_have_one_in_order(client, make_scripted_game):
    def setup(client_, host, wid):
        for slot, line in ((1, "안녕하세요, 저는 의사입니다."), (3, "집사입니다. 잘 부탁드립니다.")):
            assert client_.patch(f"/api/works/{wid}/characters/{slot}", headers=host.headers, json={"소개": line}).status_code == 200
    host, others, _, _ = make_scripted_game([("캐릭터 선택", CHARACTER_SELECT, None), ("자기소개", INTRO, None)], setup=setup)
    people = [host, *others]
    all_pick(client, people)
    assert advance(client, host).status_code == 200
    for who in people:
        view = state(client, who).json()
        board = tab(view, "자기소개")
        assert board is not None and block(view, "안내")["내용"] == "한 사람씩 자기소개를 해 주세요."
        assert board["내용"] == "인물0\n안녕하세요, 저는 의사입니다.\n\n인물2\n집사입니다. 잘 부탁드립니다."   # 멘트가 있는 인물만, 인물 순서대로
        assert "None" not in board["내용"] and "의사)" not in board["내용"]                               # 직업·닉네임은 캐릭터 설명 탭의 몫이다


def test_intro_without_any_line_makes_no_tab(client, make_scripted_game):
    def setup(client_, host, wid):
        assert client_.patch(f"/api/works/{wid}/characters/1", headers=host.headers, json={"소개": None}).status_code == 200
    host, others, _, _ = make_scripted_game([("캐릭터 선택", CHARACTER_SELECT, None), ("자기소개", INTRO, None)], setup=setup)
    all_pick(client, [host, *others])
    advance(client, host)
    view = state(client, host).json()
    assert tab(view, "자기소개") is None and block(view, "안내") is not None


def test_intro_tab_stays_by_default_and_goes_away_with_the_keep_setting_off(client, make_scripted_game):
    def setup(client_, host, wid):
        assert client_.patch(f"/api/works/{wid}/characters/1", headers=host.headers, json={"소개": "의사입니다."}).status_code == 200
    for settings, stays in ((None, True), ({"내용유지": False}, False)):
        host, others, _, _ = make_scripted_game([("캐릭터 선택", CHARACTER_SELECT, None), ("자기소개", INTRO, settings), ("빈", "", None)], setup=setup)
        all_pick(client, [host, *others])
        advance(client, host)
        assert tab(state(client, host).json(), "자기소개") is not None             # 그 단계에서는 보인다
        advance(client, host)
        assert (tab(state(client, others[0]).json(), "자기소개") is not None) is stays


@pytest.mark.parametrize("value", ["abc", 9999, None, [1], {"a": 1}, True])
def test_bad_character_values_do_not_break_character_select(client, make_scripted_game, value):
    host, others, _, _ = two_phase_game(make_scripted_game)
    qid = block(state(client, host).json(), "캐릭터 선택")["질문ID"]
    res = answer(client, host, qid, value)
    assert res.status_code == 200 and res.json()["나"]["인물_순서"] is None
    assert state(client, host).json()["오류"] == []                            # 플레이어가 보낸 값 때문에 카드가 멈추지 않는다
    assert [n["글"] for n in res.json()["알림"]] == ["이미 다른 사람이 고른 인물입니다"]
    slot = block(state(client, host).json(), "캐릭터 선택")["항목"][0]["값"]
    assert pick(client, host, slot).json()["나"]["인물_순서"] == slot            # 이후에도 정상 동작한다


# ---- 밀담·추리 발표와 기본 진행단계 목록 ------------------------------------------------------------

def test_secret_talk_and_deduction_show_their_announcement_and_settings_replace_it(client, make_scripted_game):
    from app.default_phases import DEDUCTION, SECRET_TALK

    host, others, _, _ = make_scripted_game([
        ("밀담", SECRET_TALK, None), ("추리 발표", DEDUCTION, {"안내": "한 사람당 1분씩 발표합니다."}),
    ])
    assert "밀담을 할 수 있는 단계" in block(state(client, others[0]).json(), "밀담")["내용"]
    assert advance(client, host).status_code == 200
    assert block(state(client, others[0]).json(), "추리 발표")["내용"] == "한 사람당 1분씩 발표합니다."


def test_every_common_phase_script_passes_the_same_check_as_confirm():
    from app.cards import known_names
    from app.default_phases import COMMON_PHASES
    from app.script import compile_source

    names = [name for name, *_ in COMMON_PHASES]
    assert len(names) == len(set(names))
    for name, description, source, _settings in COMMON_PHASES:
        assert description and "실행" in compile_source(source, known_names()).funcs, name


def test_profile_shows_the_chosen_items_in_one_tab_with_sections(client, make_scripted_game):
    def setup(client_, host, wid):
        for slot in (1, 2, 3):
            res = client_.patch(f"/api/works/{wid}/characters/{slot}", headers=host.headers, json={"타임라인": f"타임라인{slot}", "목표": f"목표{slot}", "능력": f"능력{slot}"})
            assert res.status_code == 200, res.text
    cards = [("캐릭터 선택", CHARACTER_SELECT, None), ("프로필 숙지", PROFILE, {"보일항목": ["비밀", "능력"]})]
    host, others, _, _ = make_scripted_game(cards, setup=setup)
    people = [host, *others]
    all_pick(client, people)
    assert advance(client, host).status_code == 200
    for who in people:
        view = state(client, who).json()
        n = view["나"]["인물_순서"]
        text = tab(view, "개인 서사")["내용"]
        assert text.startswith("▶ 비밀\n") and f"▶ 능력\n능력{n}" in text
        assert "▶ 서사" not in text and "타임라인" not in text and "목표" not in text            # 고르지 않은 항목은 보이지 않는다


def test_profile_default_shows_every_item_in_order(client, make_scripted_game):
    def setup(client_, host, wid):
        res = client_.patch(f"/api/works/{wid}/characters/1", headers=host.headers, json={"타임라인": "밤 9시 서재", "목표": "유산을 지킨다", "능력": "거짓말을 알아챈다"})
        assert res.status_code == 200
    host, others, _, _ = make_scripted_game([("캐릭터 선택", CHARACTER_SELECT, None), ("프로필 숙지", PROFILE, None)], setup=setup)
    people = [host, *others]
    all_pick(client, people)
    assert advance(client, host).status_code == 200
    mine = next(state(client, w).json() for w in people if state(client, w).json()["나"]["인물_순서"] == 1)
    text = tab(mine, "개인 서사")["내용"]
    heads = [line for line in text.split("\n") if line.startswith("▶ ")]
    assert heads == ["▶ 서사", "▶ 타임라인", "▶ 비밀", "▶ 목표", "▶ 능력"]
