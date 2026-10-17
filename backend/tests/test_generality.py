"""일반성 점검(단계 5): 기본 진행단계에 없는 모양 — 모두가 동시에 한 줄로 답하고, 다 모이면 한꺼번에 공개 — 을 같은 부품으로 만든다.

새 부품은 글자를 받는 `입력` 블록과 그 답의 검사뿐이다. 나머지(보이기, 기다리기, 현황, 대상별 화면, 단계 넘기기)는 기본 흐름이 쓰던 것 그대로이다.
"""
import pytest

from test_cards import answer, block, db, make_scripted_game, players_of, state  # noqa: F401  (픽스처 포함)
from test_game import advance

SIMULTANEOUS = '''
def 실행(카드):
    답 = {}
    모두.보이기(입력("한 줄 답변", "범인은 누구라고 생각하시나요?", 20))
    모두.보이기(현황("답변 완료", 0, 플레이어수()))
    while len(답) < 플레이어수():
        받음 = 기다리기("한 줄 답변")
        답[받음.플레이어.계정] = 받음.값
        받음.플레이어.보이기(글("한 줄 답변", "제출했습니다. 다른 사람을 기다리는 중입니다."))
        모두.보이기(현황("답변 완료", len(답), 플레이어수()))
    줄 = []
    for 플레이어 in 플레이어들():
        줄.append(플레이어.이름 + ": " + 답[플레이어.계정])
    모두.보이기(글("모두의 답변", "\\n".join(줄)))
'''


def three(make_scripted_game):
    return make_scripted_game([("한 줄 답변", SIMULTANEOUS, None)])


def test_everyone_sees_the_input_and_progress(client, make_scripted_game):
    host, others, _, _ = three(make_scripted_game)
    view = state(client, others[0]).json()
    box = block(view, "한 줄 답변")
    assert box["종류"] == "입력" and box["질문"] == "범인은 누구라고 생각하시나요?" and box["글자수"] == 20
    assert block(view, "답변 완료")["완료"] == 0 and block(view, "답변 완료")["전체"] == 3
    assert block(view, "모두의 답변") is None


def test_answers_stay_hidden_until_everyone_has_answered_then_are_revealed_together(client, make_scripted_game):
    host, others, _, _ = three(make_scripted_game)
    people = players_of(host, others)
    qid = block(state(client, host).json(), "한 줄 답변")["질문ID"]
    assert answer(client, people[0], qid, "집사").status_code == 200
    assert answer(client, people[1], qid, "의사").status_code == 200
    for who in people:
        view = state(client, who).json()
        assert block(view, "답변 완료")["완료"] == 2
        assert block(view, "모두의 답변") is None
        assert "집사" not in str([b for b in view["화면"] if b["이름"] != "한 줄 답변"])  # 남의 답이 새지 않는다
    mine = block(state(client, people[0]).json(), "한 줄 답변")
    assert mine["종류"] == "글" and "제출했습니다" in mine["내용"]                      # 낸 사람 화면은 입력칸이 안내로 바뀐다
    assert block(state(client, people[2]).json(), "한 줄 답변")["종류"] == "입력"       # 아직 안 낸 사람은 그대로
    assert answer(client, people[2], qid, "하녀").status_code == 200
    nick = {p["계정_번호"]: p["닉네임"] for p in state(client, host).json()["플레이어"]}
    expected = sorted(f"{nick[who.number]}: {text}" for who, text in zip(people, ["집사", "의사", "하녀"]))
    for who in people:
        revealed = block(state(client, who).json(), "모두의 답변")["내용"]
        assert sorted(revealed.split("\n")) == expected                                # 모두에게 같은 내용이 한꺼번에 공개된다


def test_observer_sees_progress_and_result_but_cannot_answer(client, make_scripted_game):
    host, others, _, _ = make_scripted_game([("한 줄 답변", SIMULTANEOUS, None)], players=2, observer_host=True)
    qid = block(state(client, host).json(), "한 줄 답변")["질문ID"]
    assert answer(client, host, qid, "관전자의 답").status_code == 403
    for who in others:
        assert answer(client, who, qid, "답").status_code == 200
    view = state(client, host).json()
    assert block(view, "답변 완료")["완료"] == 2 and block(view, "모두의 답변") is not None


@pytest.mark.parametrize("value, code", [("", 422), ("   ", 422), ("가" * 21, 422), (123, 422), (["a"], 422), (None, 422)])
def test_invalid_answers_are_rejected_without_changing_state(client, make_scripted_game, value, code):
    host, others, _, _ = three(make_scripted_game)
    qid = block(state(client, host).json(), "한 줄 답변")["질문ID"]
    version = state(client, host).json()["상태_버전"]
    assert answer(client, others[0], qid, value).status_code == code
    assert state(client, host).json()["상태_버전"] == version


def test_late_answer_after_everyone_answered_is_stale(client, make_scripted_game):
    host, others, _, _ = three(make_scripted_game)
    qid = block(state(client, host).json(), "한 줄 답변")["질문ID"]
    for who in players_of(host, others):
        assert answer(client, who, qid, "답").status_code == 200
    assert answer(client, host, qid, "한 번 더").status_code == 409


def test_resubmitting_replaces_the_players_earlier_answer(client, make_scripted_game):
    host, others, _, _ = three(make_scripted_game)
    qid = block(state(client, host).json(), "한 줄 답변")["질문ID"]
    answer(client, host, qid, "처음")
    answer(client, host, qid, "고침")           # 이미 낸 사람이 다시 보내도 사람 수로는 한 명이다(스크립트가 계정으로 모은다)
    assert block(state(client, host).json(), "답변 완료")["완료"] == 1
    answer(client, others[0], qid, "둘")
    answer(client, others[1], qid, "셋")
    text = block(state(client, host).json(), "모두의 답변")["내용"]
    assert "고침" in text and "처음" not in text


def test_the_new_phase_composes_with_the_default_ones(client, make_scripted_game):
    from app.default_phases import PROLOGUE

    host, others, _, _ = make_scripted_game([("프롤로그", PROLOGUE, None), ("한 줄 답변", SIMULTANEOUS, None)])
    assert advance(client, host).status_code == 200
    view = state(client, others[0]).json()
    assert block(view, "한 줄 답변")["종류"] == "입력"
    assert any(t["이름"] == "공통 스토리" for t in view["탭"])        # 앞 단계의 탭은 그대로 남는다


def test_block_name_validation_for_input(client, make_scripted_game):
    host, _, _, _ = make_scripted_game([("나쁜 입력", "def 실행(카드):\n    모두.보이기(입력('a:b', '질문'))", None)])
    assert "입력의 이름" in state(client, host).json()["오류"][0]["메시지"]
