"""토론: 얻은 단서를 보여 주고 양도한다 (app/clues.py, 토론 단계의 결정)."""
import pytest

from app.default_phases import DISCUSSION

from test_cards import answer, block, db, make_scripted_game, players_of, state, tab  # noqa: F401  (픽스처 포함)
from test_game import advance
from test_investigation import INVESTIGATE, build


def start(client, make_scripted_game, settings=None):
    """조사 → 토론. 조사에서 서재의 단서 둘(찢어진 편지, 깨진 안경)과 정원의 증언을 얻은 뒤 토론으로 넘어간다."""
    host, others, room, wid = make_scripted_game([("조사", INVESTIGATE, {"횟수": 3}), ("토론", DISCUSSION, settings)], setup=build)
    people = players_of(host, others)
    view = state(client, people[0]).json()
    choice = block(view, "조사 대상")
    answer(client, people[0], choice["질문ID"], "단서:1")      # 찢어진 편지
    answer(client, people[0], choice["질문ID"], "증언:2")      # 정원사의 증언
    answer(client, people[1], choice["질문ID"], "단서:2")      # 깨진 안경
    assert advance(client, host).status_code == 200
    return host, others, people, room


def clue_cards(client, who):
    return {c["이름"]: c for c in (tab(state(client, who).json(), "내 단서") or {"항목": []})["항목"]}


def act(client, who, action, clue, targets):
    qid = tab(state(client, who).json(), "내 단서")["질문ID"]
    return answer(client, who, qid, {"동작": action, "단서": clue, "대상": targets})


def acct(who):
    return who.number


def test_my_clues_tab_offers_actions_and_marks_what_can_be_transferred(client, make_scripted_game):
    host, others, people, _ = start(client, make_scripted_game)
    view = state(client, people[0]).json()
    mine = tab(view, "내 단서")
    assert mine["동작"] == ["보여주기", "양도"] and mine["질문ID"]
    cards = {c["이름"]: c for c in mine["항목"]}
    assert set(cards) == {"찢어진 편지", "정원사의 증언"}
    assert cards["찢어진 편지"]["양도가능"] is True and cards["찢어진 편지"]["공개"] == []
    assert cards["정원사의 증언"]["양도가능"] is False and "공개" not in cards["정원사의 증언"]   # 증언은 보여 주기·양도가 안 된다


def giver_name_in(text, client, who):
    return any(p["닉네임"] in text for p in state(client, who).json()["플레이어"])


def test_show_a_clue_to_one_person_only(client, make_scripted_game):
    host, others, people, _ = start(client, make_scripted_game)
    giver, friend, stranger = people
    letter = clue_cards(client, giver)["찢어진 편지"]["순서"]
    assert act(client, giver, "보여주기", letter, [acct(friend)]).status_code == 200
    seen = tab(state(client, friend).json(), "공개된 단서")["항목"]
    assert [c["이름"] for c in seen] == ["찢어진 편지"] and giver_name_in(seen[0]["주인"], client, giver)
    assert tab(state(client, stranger).json(), "공개된 단서")["항목"] == []
    assert "편지 내용 XYZ1" not in state(client, stranger).text                      # 보여 주지 않은 사람에게는 내용이 가지 않는다
    assert clue_cards(client, giver)["찢어진 편지"]["공개"] == [acct(friend)]


def test_show_to_several_then_everyone_then_cancel(client, make_scripted_game, db):
    host, others, people, room = start(client, make_scripted_game)
    giver, b, c = people
    letter = clue_cards(client, giver)["찢어진 편지"]["순서"]
    act(client, giver, "보여주기", letter, [acct(b), acct(c)])
    for who in (b, c):
        assert len(tab(state(client, who).json(), "공개된 단서")["항목"]) == 1
    act(client, giver, "보여주기", letter, "전체")
    assert clue_cards(client, giver)["찢어진 편지"]["공개"] == "전체"
    for who in (b, c):
        assert len(tab(state(client, who).json(), "공개된 단서")["항목"]) == 1
    act(client, giver, "보여주기", letter, [])                                        # 취소
    for who in (b, c):
        assert tab(state(client, who).json(), "공개된 단서")["항목"] == []
        assert "XYZ1" not in state(client, who).text
    rows = db.execute(
        'SELECT 대상_참여_번호 IS NULL, 취소일시 IS NOT NULL FROM "공개" WHERE 진행_번호 = (SELECT 번호 FROM "진행" WHERE 방_번호 = %s) ORDER BY 번호',
        (room["번호"],),
    ).fetchall()
    assert rows == [(False, True), (False, True), (True, True)]                       # 한 명, 한 명, 전체. 모두 취소됨


def test_transfer_is_immediate_and_clears_reveals(client, make_scripted_game, db):
    host, others, people, room = start(client, make_scripted_game)
    giver, taker, third = people
    letter = clue_cards(client, giver)["찢어진 편지"]["순서"]
    act(client, giver, "보여주기", letter, [acct(third)])
    assert act(client, giver, "양도", letter, [acct(taker)]).status_code == 200
    assert "찢어진 편지" not in clue_cards(client, giver)
    assert clue_cards(client, taker)["찢어진 편지"]["공개"] == []                       # 받은 단서에는 이전 공개가 남아 있지 않다
    assert tab(state(client, third).json(), "공개된 단서")["항목"] == []                 # 양도하면 걸린 공개는 사라진다
    assert [n["글"] for n in state(client, taker).json()["알림"]][-1].endswith("단서를 넘겨주었습니다.")
    rows = db.execute(
        'SELECT 획득방법, 보유여부 FROM "획득" WHERE 단서_순서 = %s AND 진행_번호 = (SELECT 번호 FROM "진행" WHERE 방_번호 = %s) ORDER BY 번호',
        (letter, room["번호"]),
    ).fetchall()
    assert rows == [("조사", False), ("양도", True)]
    active = db.execute(
        'SELECT count(*) FROM "공개" WHERE 취소일시 IS NULL AND 진행_번호 = (SELECT 번호 FROM "진행" WHERE 방_번호 = %s)', (room["번호"],)
    ).fetchone()[0]
    assert active == 0
    # 받은 사람은 다시 넘기거나 보여 줄 수 있다
    assert act(client, taker, "양도", letter, [acct(third)]).status_code == 200
    assert "찢어진 편지" in clue_cards(client, third)


def test_testimony_cannot_be_shown_or_transferred(client, make_scripted_game):
    host, others, people, _ = start(client, make_scripted_game)
    giver, friend, _ = people
    testimony = clue_cards(client, giver)["정원사의 증언"]["순서"]                      # 증언 순서(단서 순서와 별도로 센다)
    held_clue_orders = {c["순서"] for c in clue_cards(client, giver).values() if c["종류"] == "단서"}
    probe = testimony if testimony not in held_clue_orders else 99
    res = act(client, giver, "양도", probe, [acct(friend)])
    assert res.status_code == 200 and [n["글"] for n in res.json()["알림"]][-1] == "넘겨 줄 수 없는 단서입니다."
    assert "정원사의 증언" in clue_cards(client, giver) and "정원사의 증언" not in clue_cards(client, friend)


def test_cannot_move_a_clue_you_do_not_hold(client, make_scripted_game):
    host, others, people, _ = start(client, make_scripted_game)
    giver, friend, third = people
    glasses = clue_cards(client, friend)["깨진 안경"]["순서"]                           # 다른 사람의 단서
    for action, targets in (("양도", [acct(third)]), ("보여주기", [acct(third)])):
        res = act(client, giver, action, glasses, targets)
        assert res.status_code == 200 and res.json()["알림"][-1]["글"].endswith("단서입니다.")
    assert "깨진 안경" in clue_cards(client, friend) and "깨진 안경" not in clue_cards(client, giver)


@pytest.mark.parametrize("value", [
    "abc", None, 5, [1], {}, {"동작": "양도"}, {"동작": "교환", "단서": 1, "대상": []},
    {"동작": "양도", "단서": "1", "대상": [2]}, {"동작": "양도", "단서": True, "대상": [2]},
    {"동작": "양도", "단서": 1, "대상": []}, {"동작": "양도", "단서": 1, "대상": "전체"},
    {"동작": "양도", "단서": 1, "대상": [999999]}, {"동작": "보여주기", "단서": 1, "대상": "모두"},
    {"동작": "보여주기", "단서": 1, "대상": [None]}, {"동작": "보여주기", "단서": 1, "대상": {"a": 1}},
])
def test_malformed_actions_are_rejected_and_the_card_keeps_working(client, make_scripted_game, value):
    host, others, people, _ = start(client, make_scripted_game)
    giver = people[0]
    qid = tab(state(client, giver).json(), "내 단서")["질문ID"]
    version = state(client, giver).json()["상태_버전"]
    assert answer(client, giver, qid, value).status_code == 422
    assert state(client, giver).json()["상태_버전"] == version and state(client, host).json()["오류"] == []
    assert act(client, giver, "보여주기", clue_cards(client, giver)["찢어진 편지"]["순서"], "전체").status_code == 200   # 계속 동작한다


def test_cannot_target_yourself(client, make_scripted_game):
    host, others, people, _ = start(client, make_scripted_game)
    giver = people[0]
    letter = clue_cards(client, giver)["찢어진 편지"]["순서"]
    assert act(client, giver, "양도", letter, [acct(giver)]).status_code == 422
    assert act(client, giver, "보여주기", letter, [acct(giver)]).status_code == 422


def test_card_settings_can_remove_actions(client, make_scripted_game):
    host, others, people, _ = start(client, make_scripted_game, settings={"양도허용": False})
    giver = people[0]
    assert tab(state(client, giver).json(), "내 단서")["동작"] == ["보여주기"]
    letter = clue_cards(client, giver)["찢어진 편지"]["순서"]
    assert act(client, giver, "양도", letter, [acct(people[1])]).status_code == 422          # 허용하지 않은 동작은 받지 않는다
    assert "찢어진 편지" in clue_cards(client, giver)


def test_observer_cannot_act_and_sees_no_buttons(client, make_scripted_game):
    obs_host, obs_others, _, _ = make_scripted_game([("토론", DISCUSSION, None)], players=2, observer_host=True, setup=build)
    view = state(client, obs_host).json()
    mine = tab(view, "내 단서")
    assert mine is None or ("동작" not in mine and "질문ID" not in mine)
    qid = tab(state(client, obs_others[0]).json(), "내 단서")["질문ID"]
    assert answer(client, obs_host, qid, {"동작": "보여주기", "단서": 1, "대상": "전체"}).status_code == 403


def test_actions_disappear_from_the_tab_after_the_phase_ends_but_cards_stay(client, make_scripted_game):
    # 토론 다음 단계가 없어 넘길 수 없으므로 한 단계를 더 가진 작품으로 확인한다
    h2, o2, _, _ = make_scripted_game([("토론", DISCUSSION, None), ("빈", "", None)], setup=build)
    p2 = players_of(h2, o2)
    qid = tab(state(client, p2[0]).json(), "내 단서")["질문ID"]
    assert advance(client, h2).status_code == 200
    after = tab(state(client, p2[0]).json(), "내 단서")
    assert after is not None and "동작" not in after and "질문ID" not in after
    assert answer(client, p2[0], qid, {"동작": "보여주기", "단서": 1, "대상": "전체"}).status_code == 409


def test_revealed_clue_shows_the_owner_by_character_and_nickname(client, make_scripted_game):
    host, others, people, _ = start(client, make_scripted_game)
    giver, friend, _ = people
    letter = clue_cards(client, giver)["찢어진 편지"]["순서"]
    act(client, giver, "보여주기", letter, [acct(friend)])
    owner = tab(state(client, friend).json(), "공개된 단서")["항목"][0]["주인"]
    assert owner and owner != "None"
