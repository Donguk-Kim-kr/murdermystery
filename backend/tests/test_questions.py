"""개인 질문: 인물마다 다른 질문에 각자 비공개로 답하고, 답은 게임 변수로 남아 엔딩 조건이 읽는다 (app/default_phases.py PERSONAL_QUESTION)."""
import pytest

from app.default_phases import CHARACTER_SELECT, ENDING, FINAL_VOTE, PERSONAL_QUESTION
from test_cards import all_pick, answer, block, db, make_scripted_game, players_of, state  # noqa: F401  (픽스처 포함)
from test_endings import api
from test_game import advance

QUESTIONS = {"질문": {"1": "당신이 본 것은 무엇입니까?", "2": {"질문": "비밀을 알고 있었습니까?", "선택": ["예", "아니오"]}}}


def asking(client, make_scripted_game, settings=QUESTIONS, endings=(), players=3, places=()):
    def setup(client_, host, wid):
        for place in places:
            api(client_, host, wid, "places", 이름=place)
        for name, condition, text in endings:
            api(client_, host, wid, "endings", 이름=name, 조건=condition, 내용=text)

    cards = [("캐릭터 선택", CHARACTER_SELECT, None), ("최종 투표", FINAL_VOTE, None), ("개인 질문", PERSONAL_QUESTION, settings), ("엔딩", ENDING, None)]
    host, others, room, wid = make_scripted_game(cards, players=players, setup=setup)
    people = players_of(host, others)
    all_pick(client, people)
    assert advance(client, host).status_code == 200
    assert advance(client, host).status_code == 200                      # 투표는 건너뛴다(방장이 넘길 수 있다)
    slots = {who.number: state(client, who).json()["나"]["인물_순서"] for who in people}
    return host, people, slots


def by_slot(people, slots):
    return {slots[who.number]: who for who in people}


def test_each_player_sees_only_their_own_question(client, make_scripted_game):
    host, people, slots = asking(client, make_scripted_game)
    who = by_slot(people, slots)
    first = state(client, who[1]).json()
    box = block(first, "개인 질문")
    assert box["종류"] == "입력" and box["질문"] == "당신이 본 것은 무엇입니까?"
    second = state(client, who[2]).json()
    box2 = block(second, "개인 질문")
    assert box2["종류"] == "투표" and box2["문구"] == "답변" and box2["질문"] == "비밀을 알고 있었습니까?"
    assert [i["이름"] for i in box2["항목"]] == ["예", "아니오"]
    third = state(client, who[3]).json()
    assert block(third, "개인 질문")["종류"] == "글" and "질문이 없습니다" in block(third, "개인 질문")["내용"]
    assert "비밀을 알고 있었습니까" not in str(first) and "당신이 본 것은" not in str(second)       # 남의 질문은 어디에도 없다
    assert "당신이 본 것은" not in str(third) and "비밀을 알고 있었습니까" not in str(third)
    assert block(first, "답변 완료")["완료"] == 0 and block(first, "답변 완료")["전체"] == 2   # 질문이 있는 사람만 센다


def test_free_text_and_choice_answers_are_saved_as_variables_and_progress_is_shared(client, make_scripted_game):
    endings = [
        ("본 것", {"식": '변수("개인 질문:1") == "범인의 얼굴"'}, "목격자 엔딩"),
        ("비밀 앎", {"식": '변수("개인 질문:2") == "예"'}, "비밀을 알았다"),
        ("비밀 모름", {"식": '변수("개인 질문:2") == "아니오"'}, "비밀을 몰랐다"),
    ]
    host, people, slots = asking(client, make_scripted_game, endings=endings)
    who = by_slot(people, slots)
    box = block(state(client, who[1]).json(), "개인 질문")
    assert answer(client, who[1], box["질문ID"], "범인의 얼굴").status_code == 200
    for p in people:
        assert block(state(client, p).json(), "답변 완료")["완료"] == 1
    assert "내 답변: 범인의 얼굴" in block(state(client, who[1]).json(), "개인 질문 내 답변")["내용"]
    assert block(state(client, who[2]).json(), "개인 질문 내 답변") is None
    box2 = block(state(client, who[2]).json(), "개인 질문")
    assert answer(client, who[2], box2["질문ID"], "아니오").status_code == 200
    assert block(state(client, who[3]).json(), "답변 완료")["완료"] == 2
    assert advance(client, host).status_code == 200
    shown = sorted(b["이름"] for b in state(client, who[3]).json()["화면"])
    assert shown == ["엔딩: 본 것", "엔딩: 비밀 모름"]                          # 답에 따라 엔딩이 갈린다


def test_answers_can_be_changed_until_the_phase_ends(client, make_scripted_game):
    endings = [("예", {"식": '변수("개인 질문:2") == "예"'}, "예 엔딩"), ("아니오", {"식": '변수("개인 질문:2") == "아니오"'}, "아니오 엔딩")]
    host, people, slots = asking(client, make_scripted_game, endings=endings)
    who = by_slot(people, slots)
    qid = block(state(client, who[2]).json(), "개인 질문")["질문ID"]
    answer(client, who[2], qid, "예")
    answer(client, who[2], qid, "아니오")
    assert block(state(client, who[2]).json(), "답변 완료")["완료"] == 1           # 바꿔도 한 명으로 센다
    advance(client, host)
    assert [b["이름"] for b in state(client, who[1]).json()["화면"]] == ["엔딩: 아니오"]


@pytest.mark.parametrize("value", [None, 5, ["예"], {"a": 1}, True, "", "가" * 301])
def test_malformed_free_text_answers_are_rejected(client, make_scripted_game, value):
    host, people, slots = asking(client, make_scripted_game)
    who = by_slot(people, slots)
    qid = block(state(client, who[1]).json(), "개인 질문")["질문ID"]
    assert answer(client, who[1], qid, value).status_code == 422
    assert state(client, host).json()["오류"] == [] and block(state(client, who[1]).json(), "답변 완료")["완료"] == 0


@pytest.mark.parametrize("value", ["모르겠다", 5])
def test_answers_outside_the_choices_are_refused_with_a_notice_and_the_card_keeps_working(client, make_scripted_game, value):
    host, people, slots = asking(client, make_scripted_game)
    who = by_slot(people, slots)
    qid = block(state(client, who[2]).json(), "개인 질문")["질문ID"]
    res = answer(client, who[2], qid, value)
    assert res.status_code == 200 and res.json()["알림"][-1]["글"] == "고를 수 없는 답입니다."
    assert state(client, host).json()["오류"] == [] and block(state(client, who[2]).json(), "답변 완료")["완료"] == 0
    assert answer(client, who[2], qid, "예").status_code == 200


@pytest.mark.parametrize("value", [None, ["예"], {"a": 1}, ""])
def test_unreadable_choice_answers_are_rejected(client, make_scripted_game, value):
    host, people, slots = asking(client, make_scripted_game)
    who = by_slot(people, slots)
    qid = block(state(client, who[2]).json(), "개인 질문")["질문ID"]
    assert answer(client, who[2], qid, value).status_code == 422
    assert state(client, host).json()["오류"] == [] and block(state(client, who[2]).json(), "답변 완료")["완료"] == 0


def test_a_player_without_a_question_cannot_answer_anyone_elses(client, make_scripted_game):
    host, people, slots = asking(client, make_scripted_game)
    who = by_slot(people, slots)
    qid = block(state(client, who[1]).json(), "개인 질문")["질문ID"]
    version = block(state(client, who[3]).json(), "답변 완료")["완료"]
    assert answer(client, who[3], qid, "몰래 답").status_code == 200           # 요청은 받지만 아무 일도 하지 않는다
    assert block(state(client, who[3]).json(), "답변 완료")["완료"] == version == 0
    assert "몰래 답" not in str(state(client, who[1]).json())


def test_malformed_question_settings_do_not_break_the_game(client, make_scripted_game):
    settings = {"질문": {"1": ["목록"], "2": {"질문": "", "선택": ["예"]}, "3": {"질문": "정상 질문", "선택": ["가", "가", "", 5], "글자수": "x"}, "x": "무시"}}
    host, people, slots = asking(client, make_scripted_game, settings=settings)
    who = by_slot(people, slots)
    assert block(state(client, who[1]).json(), "개인 질문")["종류"] == "글"       # 읽을 수 없는 질문은 없는 것으로 본다
    box = block(state(client, who[3]).json(), "개인 질문")
    assert [i["이름"] for i in box["항목"]] == ["가"] and state(client, host).json()["오류"] == []


def test_no_questions_configured_shows_a_notice_to_everyone(client, make_scripted_game):
    host, people, slots = asking(client, make_scripted_game, settings=None)
    for p in people:
        assert "질문이 없습니다" in block(state(client, p).json(), "개인 질문")["내용"]
    assert block(state(client, host).json(), "답변 완료")["전체"] == 0


def test_two_question_cards_keep_separate_variables_by_name(client, make_scripted_game):
    both = [("캐릭터 선택", CHARACTER_SELECT, None), ("1차 질문", PERSONAL_QUESTION, {"이름": "1차", "질문": {"1": "첫 질문"}}),
            ("2차 질문", PERSONAL_QUESTION, {"이름": "2차", "질문": {"1": "둘째 질문"}})]
    host, others, _, _ = make_scripted_game(both)
    people = players_of(host, others)
    all_pick(client, people)
    advance(client, host)
    who = by_slot(people, {p.number: state(client, p).json()["나"]["인물_순서"] for p in people})
    answer(client, who[1], block(state(client, who[1]).json(), "1차")["질문ID"], "A")
    advance(client, host)
    answer(client, who[1], block(state(client, who[1]).json(), "2차")["질문ID"], "B")
    game = client.app.state.games.of_account(host.number)
    assert game.variables == {"1차:1": "A", "2차:1": "B"}


def test_a_question_can_be_answered_by_picking_a_character(client, make_scripted_game):
    """답하는 방식이 '인물'이면 작품의 인물 중에서 고르고, 답은 인물 번호로 남는다."""
    settings = {"질문": {"1": {"질문": "가장 의심스러운 사람은?", "방식": "인물"}}}
    endings = [("의심", {"식": '변수("개인 질문:1") == 2'}, "2번을 의심했다")]
    host, people, slots = asking(client, make_scripted_game, settings=settings, endings=endings)
    who = by_slot(people, slots)
    box = block(state(client, who[1]).json(), "개인 질문")
    assert box["종류"] == "투표" and box["문구"] == "답변" and len(box["항목"]) == 3
    assert [i["값"] for i in box["항목"] if i["비활성"]] == [1]                          # 자기 인물은 고를 수 없다
    assert answer(client, who[1], box["질문ID"], 2).status_code == 200
    assert block(state(client, who[2]).json(), "답변 완료")["완료"] == 1
    assert advance(client, host).status_code == 200
    assert [b["이름"] for b in state(client, who[3]).json()["화면"]] == ["엔딩: 의심"]


def test_a_question_can_be_answered_by_picking_a_place(client, make_scripted_game):
    settings = {"질문": {"1": {"질문": "어디에 숨었습니까?", "방식": "장소"}}}
    endings = [("정원", {"식": '변수("개인 질문:1") == "장소:2"'}, "정원에 있었다")]
    host, people, slots = asking(client, make_scripted_game, settings=settings, endings=endings, places=("서재", "정원"))
    who = by_slot(people, slots)
    box = block(state(client, who[1]).json(), "개인 질문")
    assert [i["이름"] for i in box["항목"]] == ["서재", "정원"] and [i["값"] for i in box["항목"]] == ["장소:1", "장소:2"]
    assert answer(client, who[1], box["질문ID"], "장소:3").json()["알림"][-1]["글"] == "고를 수 없는 답입니다."
    assert answer(client, who[1], box["질문ID"], "장소:2").status_code == 200
    assert advance(client, host).status_code == 200
    assert [b["이름"] for b in state(client, who[2]).json()["화면"]] == ["엔딩: 정원"]


def test_text_and_choice_questions_can_share_one_card_name(client, make_scripted_game):
    """사람마다 방식이 달라도(글 / 선택 / 인물) 같은 카드 이름으로 각자 맞는 칸이 나오고, 긴 글 답은 선택 칸의 규칙에 막히지 않는다."""
    settings = {"질문": {"1": "느낀 점은?", "2": {"질문": "누구?", "방식": "인물"}, "3": {"질문": "예아니오", "방식": "선택", "선택": ["예", "아니오"]}}}
    host, people, slots = asking(client, make_scripted_game, settings=settings)
    who = by_slot(people, slots)
    kinds = {n: block(state(client, who[n]).json(), "개인 질문")["종류"] for n in (1, 2, 3)}
    assert kinds == {1: "입력", 2: "투표", 3: "투표"}
    long_text = "가" * 120
    assert answer(client, who[1], block(state(client, who[1]).json(), "개인 질문")["질문ID"], long_text).status_code == 200
    assert block(state(client, who[2]).json(), "답변 완료")["완료"] == 1


def test_a_choice_question_without_choices_shows_no_question(client, make_scripted_game):
    settings = {"질문": {"1": {"질문": "예아니오", "방식": "선택", "선택": []}}}
    host, people, slots = asking(client, make_scripted_game, settings=settings)
    who = by_slot(people, slots)
    assert "질문이 없습니다" in block(state(client, who[1]).json(), "개인 질문")["내용"]
    assert block(state(client, host).json(), "답변 완료")["전체"] == 0
