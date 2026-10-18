"""최종 투표: 비공개 동시 투표, 몇 명이 했는지만 보임, 다음 단계 전까지 바꾸기, 후보 지정, 동률 규칙 (app/default_phases.py FINAL_VOTE)."""
import pytest

from app.default_phases import CHARACTER_SELECT, FINAL_VOTE
from test_cards import all_pick, answer, block, db, make_scripted_game, players_of, state  # noqa: F401  (픽스처 포함)
from test_game import advance

PROBE = '''
def 실행(카드):
    구속 = 결과("최종 투표")
    if 구속 is None:
        모두.보이기(글("결과", "구속 없음"))
    else:
        모두.보이기(글("결과", 구속.이름))
'''


def voting(make_scripted_game, client, settings=None, players=3, with_probe=True):
    cards = [("캐릭터 선택", CHARACTER_SELECT, None), ("최종 투표", FINAL_VOTE, settings)]
    if with_probe:
        cards.append(("결과 확인", PROBE, None))
    host, others, room, wid = make_scripted_game(cards, players=players)
    people = players_of(host, others)
    all_pick(client, people)
    assert advance(client, host).status_code == 200
    slots = {who.number: state(client, who).json()["나"]["인물_순서"] for who in people}
    return host, people, slots


def vote(client, who, slot):
    box = block(state(client, who).json(), "최종 투표")
    return answer(client, who, box["질문ID"], slot)


def result(client, host):
    assert advance(client, host).status_code == 200
    return block(state(client, host).json(), "결과")["내용"]


def test_vote_block_lists_candidates_and_blocks_your_own_character(client, make_scripted_game):
    host, people, slots = voting(make_scripted_game, client)
    for who in people:
        view = state(client, who).json()
        box = block(view, "최종 투표")
        assert box["종류"] == "투표" and box["내_선택"] is None and len(box["항목"]) == 3
        assert [i["값"] for i in box["항목"] if i["비활성"]] == [slots[who.number]]       # 자기 인물만 고를 수 없다
        assert block(view, "투표 완료")["완료"] == 0 and block(view, "투표 완료")["전체"] == 3
        assert all("선택한_계정" not in i for i in box["항목"])


def test_progress_is_shared_but_who_voted_for_whom_is_private(client, make_scripted_game):
    host, people, slots = voting(make_scripted_game, client)
    a, b, c = people
    assert vote(client, a, slots[b.number]).status_code == 200
    for who in people:
        assert block(state(client, who).json(), "투표 완료")["완료"] == 1
    assert block(state(client, a).json(), "최종 투표")["내_선택"] == slots[b.number]
    for who in (b, c, host) if host not in (a,) else (b, c):
        assert block(state(client, who).json(), "최종 투표")["내_선택"] is None
    # 응답 어디에도 남의 선택을 알 수 있는 값이 없다
    assert '"내_선택": ' not in state(client, c).text.replace('"내_선택": null', "")


def test_a_player_can_change_the_vote_until_the_phase_ends(client, make_scripted_game):
    host, people, slots = voting(make_scripted_game, client)
    a, b, c = people
    qid = block(state(client, a).json(), "최종 투표")["질문ID"]
    vote(client, a, slots[b.number])
    vote(client, a, slots[c.number])
    box = block(state(client, a).json(), "최종 투표")
    assert box["내_선택"] == slots[c.number]
    assert block(state(client, a).json(), "투표 완료")["완료"] == 1                       # 바꿔도 한 명으로 센다
    assert advance(client, host).status_code == 200
    assert answer(client, a, qid, slots[b.number]).status_code == 409                    # 다음 단계로 넘어간 뒤에는 바꿀 수 없다


def test_voting_for_yourself_or_a_non_candidate_is_refused_with_a_notice(client, make_scripted_game):
    host, people, slots = voting(make_scripted_game, client)
    a = people[0]
    for value in (slots[a.number], 99999):
        res = vote(client, a, value)
        assert res.status_code == 200 and res.json()["알림"][-1]["글"] == "이 인물에게는 투표할 수 없습니다."
    assert block(state(client, a).json(), "투표 완료")["완료"] == 0


@pytest.mark.parametrize("value", ["abc", None, [1], {"a": 1}, 1.5, True])
def test_malformed_vote_values_are_rejected_and_the_card_keeps_working(client, make_scripted_game, value):
    host, people, slots = voting(make_scripted_game, client)
    a, b, _ = people
    qid = block(state(client, a).json(), "최종 투표")["질문ID"]
    version = state(client, a).json()["상태_버전"]
    assert answer(client, a, qid, value).status_code == 422
    assert state(client, a).json()["상태_버전"] == version and state(client, host).json()["오류"] == []
    assert vote(client, a, slots[b.number]).status_code == 200


def test_observer_sees_progress_but_cannot_vote(client, make_scripted_game):
    host, others, _, _ = make_scripted_game([("캐릭터 선택", CHARACTER_SELECT, None), ("최종 투표", FINAL_VOTE, None)], players=2, observer_host=True)
    all_pick(client, others)
    assert advance(client, others[0]).status_code == 200
    box = block(state(client, host).json(), "최종 투표")
    assert all(i["비활성"] for i in box["항목"]) and box["내_선택"] is None
    assert answer(client, host, box["질문ID"], box["항목"][0]["값"]).status_code == 403


def test_result_is_the_unique_top_vote_getter_and_none_for_ties_or_no_votes(client, make_scripted_game):
    host, people, slots = voting(make_scripted_game, client)
    a, b, c = people
    nobody = voting(make_scripted_game, client)       # 투표가 하나도 없는 별도 게임
    assert result(client, nobody[0]) == "구속 없음"
    vote(client, a, slots[c.number])
    vote(client, b, slots[c.number])
    vote(client, c, slots[a.number])
    name = {i["값"]: i["이름"] for i in block(state(client, a).json(), "최종 투표")["항목"]}[slots[c.number]]
    assert result(client, host) == name                                                  # 2표 대 1표


def test_tie_without_revote_rule_means_no_arrest(client, make_scripted_game):
    host, people, slots = voting(make_scripted_game, client)
    a, b, c = people
    vote(client, a, slots[b.number])
    vote(client, b, slots[c.number])
    vote(client, c, slots[a.number])                                                    # 1-1-1
    assert block(state(client, a).json(), "투표 완료")["완료"] == 3                       # 기본 동률 규칙은 구속 없음: 다시 투표하지 않는다
    assert result(client, host) == "구속 없음"


def test_partial_votes_can_be_advanced_by_the_host_and_still_count(client, make_scripted_game):
    host, people, slots = voting(make_scripted_game, client)
    a, b, c = people
    vote(client, a, slots[c.number])                                                    # 한 명만 투표했다
    assert advance(client, host).status_code == 200                                      # 방장은 그대로 넘길 수 있다
    assert block(state(client, host).json(), "결과")["내용"] != "구속 없음"


def test_revote_on_tie_resets_votes_and_notifies_everyone(client, make_scripted_game):
    host, people, slots = voting(make_scripted_game, client, settings={"동률": "재투표", "재투표한도": 1})
    a, b, c = people
    vote(client, a, slots[b.number])
    vote(client, b, slots[c.number])
    vote(client, c, slots[a.number])                                                    # 1-1-1 동률 → 재투표
    for who in people:
        view = state(client, who).json()
        assert block(view, "투표 완료")["완료"] == 0 and block(view, "최종 투표")["내_선택"] is None
        assert block(view, "최종 투표")["질문"].endswith("(2차)")
        assert view["알림"][-1]["글"] == "동률입니다. 재투표를 진행합니다."
    vote(client, a, slots[b.number])
    vote(client, b, slots[c.number])
    vote(client, c, slots[a.number])                                                    # 또 동률이지만 한도(1)를 넘어 더 하지 않는다
    assert block(state(client, a).json(), "투표 완료")["완료"] == 3
    assert result(client, host) == "구속 없음"


def test_revote_limit_zero_repeats_until_the_tie_breaks(client, make_scripted_game):
    host, people, slots = voting(make_scripted_game, client, settings={"동률": "재투표", "재투표한도": 0})
    a, b, c = people
    for _ in range(3):                                                                   # 동률이 풀릴 때까지 몇 번이든
        vote(client, a, slots[b.number])
        vote(client, b, slots[c.number])
        vote(client, c, slots[a.number])
        assert block(state(client, a).json(), "투표 완료")["완료"] == 0
    vote(client, a, slots[c.number])
    vote(client, b, slots[c.number])
    vote(client, c, slots[a.number])
    assert block(state(client, a).json(), "투표 완료")["완료"] == 3 and result(client, host) != "구속 없음"


@pytest.mark.parametrize("scope, expected", [("동률자만", 2), ("전체", 4)])
def test_revote_candidates_are_the_tied_ones_or_everyone(client, make_scripted_game, scope, expected):
    host, people, slots = voting(make_scripted_game, client, settings={"동률": "재투표", "재투표후보": scope}, players=4)
    p0, p1, p2, p3 = people
    vote(client, p0, slots[p1.number])
    vote(client, p1, slots[p0.number])
    vote(client, p2, slots[p1.number])
    vote(client, p3, slots[p0.number])                                                   # p0·p1 의 인물이 2표씩
    assert len(block(state(client, p2).json(), "최종 투표")["항목"]) == expected


def test_candidates_can_be_designated_by_the_maker(client, make_scripted_game):
    host, people, slots = voting(make_scripted_game, client, settings={"후보": [1, 2, 99]})
    a = people[0]
    box = block(state(client, a).json(), "최종 투표")
    assert [i["값"] for i in box["항목"]] == [1, 2]                                       # 없는 번호는 건너뛴다
    outside = next(s for s in slots.values() if s not in (1, 2))
    assert vote(client, a, outside).json()["알림"][-1]["글"] == "이 인물에게는 투표할 수 없습니다."


def test_vote_results_never_leak_into_other_players_state(client, make_scripted_game):
    host, people, slots = voting(make_scripted_game, client)
    a, b, c = people
    vote(client, a, slots[c.number])
    vote(client, b, slots[c.number])
    assert block(state(client, c).json(), "최종 투표")["내_선택"] is None            # 아직 투표하지 않은 사람은 남의 표를 알 수 없다
    assert block(state(client, a).json(), "최종 투표")["내_선택"] == slots[c.number]
    assert block(state(client, b).json(), "최종 투표")["내_선택"] == slots[c.number]
    for who in people:
        assert "득표" not in state(client, who).text and "구속" not in state(client, who).text
