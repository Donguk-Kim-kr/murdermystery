"""공통 스토리: 개인 서사처럼 부분(최대 5)으로 나누고, 카드가 보여 줄 부분과 탭 이름·방식을 정한다 (app/default_phases.py PROLOGUE, PROFILE)."""
import pytest

from app import narrative
from app.cards import _ordinal_prefix
from app.default_phases import PROFILE, PROLOGUE
from test_cards import advance, all_pick, answer, block, db, make_scripted_game, players_of, state, tab  # noqa: F401  (픽스처 포함)
from test_cards import CHARACTER_SELECT

PARTS = [{"ID": None, "본문": "첫째 부분"}, {"ID": None, "본문": "둘째 부분"}, {"ID": None, "본문": "셋째 부분"}]


def story_game(make_scripted_game, cards):
    def setup(client_, host, wid):
        res = client_.patch(f"/api/works/{wid}", headers=host.headers, json={"공통스토리_부분": PARTS})
        assert res.status_code == 200, res.text
    return make_scripted_game(cards, setup=setup)


def test_work_story_is_saved_as_parts_and_returned_without_markers(client, headers):
    w = client.post("/api/works", headers=headers, json={"제목": "작품", "공통스토리": "한 덩어리 글"}).json()
    assert w["공통스토리"] == "한 덩어리 글" and [p["본문"] for p in w["공통스토리_부분"]] == ["한 덩어리 글"]
    res = client.patch(f"/api/works/{w['번호']}", headers=headers, json={"공통스토리_부분": PARTS})
    assert res.status_code == 200
    got = res.json()
    assert [p["본문"] for p in got["공통스토리_부분"]] == ["첫째 부분", "둘째 부분", "셋째 부분"] and all(p["ID"] for p in got["공통스토리_부분"])
    assert got["공통스토리"] == "첫째 부분\n\n둘째 부분\n\n셋째 부분" and "@@MMPART" not in got["공통스토리"]
    kept = got["공통스토리_부분"]                                                     # ID 를 그대로 보내면 같은 부분으로 이어진다
    again = client.patch(f"/api/works/{w['번호']}", headers=headers, json={"공통스토리_부분": [kept[0], {"ID": None, "본문": "새 부분"}]}).json()
    assert again["공통스토리_부분"][0]["ID"] == kept[0]["ID"] and [p["본문"] for p in again["공통스토리_부분"]] == ["첫째 부분", "새 부분"]


@pytest.mark.parametrize("parts, message", [
    ([{"ID": None, "본문": "a"}] * 6, "5개까지"),
    ([{"ID": None, "본문": "  "}], "비어"),
    ([{"ID": None, "본문": "x" * 10001}, {"ID": None, "본문": "y"}, {"ID": None, "본문": "z"}], "너무 깁니다"),
    ([{"ID": None, "본문": "@@MMPART:abcdef@@"}], "예약된"),
])
def test_bad_story_parts_are_refused(client, headers, parts, message):
    w = client.post("/api/works", headers=headers, json={"제목": "작품"}).json()["번호"]
    res = client.patch(f"/api/works/{w}", headers=headers, json={"공통스토리_부분": parts})
    assert res.status_code == 422 and message in res.json()["detail"] and "공통 스토리" in res.json()["detail"]
    both = client.patch(f"/api/works/{w}", headers=headers, json={"공통스토리": "글", "공통스토리_부분": PARTS})
    assert both.status_code == 422


def test_ordinal_prefix_is_empty_for_the_first_card_and_numbered_after():
    assert _ordinal_prefix("공통 스토리", "공통 스토리") == ""
    assert _ordinal_prefix("1차 공통 스토리", "공통 스토리") == ""
    assert _ordinal_prefix("2차 공통 스토리", "공통 스토리") == "2차 "
    assert _ordinal_prefix("3차 공통 스토리", "공통 스토리") == "3차 "
    assert _ordinal_prefix("2차 조사", "공통 스토리") == ""


def test_card_shows_the_chosen_parts_and_by_default_only_the_first(client, make_scripted_game):
    host, others, _, _ = story_game(make_scripted_game, [("공통 스토리", PROLOGUE, None)])
    assert block(state(client, host).json(), "공통 스토리")["내용"] == "첫째 부분"
    host, others, _, _ = story_game(make_scripted_game, [("공통 스토리", PROLOGUE, {"공개부분": [1, 3]})])
    view = state(client, others[0]).json()
    assert block(view, "공통 스토리")["내용"] == "첫째 부분\n\n셋째 부분" and tab(view, "공통 스토리")["내용"] == "첫째 부분\n\n셋째 부분"


def test_a_second_card_adds_a_new_tab_by_default_and_the_first_stays(client, make_scripted_game):
    host, others, _, _ = story_game(make_scripted_game, [
        ("공통 스토리", PROLOGUE, None), ("공통 스토리", PROLOGUE, {"공개부분": [2]}),
    ])
    assert advance(client, host).status_code == 200
    view = state(client, others[0]).json()
    assert tab(view, "공통 스토리")["내용"] == "첫째 부분"                       # 앞 카드의 탭은 그대로
    assert tab(view, "2차 공통 스토리")["내용"] == "둘째 부분"                    # 둘째 카드는 새 탭
    assert block(view, "2차 공통 스토리")["내용"] == "둘째 부분"                  # 읽기 확인에도 새 부분만 보인다


def test_a_second_card_can_append_to_the_existing_tab(client, make_scripted_game):
    host, others, _, _ = story_game(make_scripted_game, [
        ("공통 스토리", PROLOGUE, None), ("공통 스토리", PROLOGUE, {"공개부분": [2, 3], "탭방식": "이어서"}),
    ])
    assert advance(client, host).status_code == 200
    view = state(client, others[0]).json()
    assert tab(view, "공통 스토리")["내용"] == "첫째 부분\n\n둘째 부분\n\n셋째 부분"
    assert tab(view, "2차 공통 스토리") is None
    assert block(view, "공통 스토리")["내용"] == "둘째 부분\n\n셋째 부분"            # 확인 화면은 새 부분만


def test_tab_name_can_be_chosen_and_the_same_name_is_replaced(client, make_scripted_game):
    host, others, _, _ = story_game(make_scripted_game, [
        ("공통 스토리", PROLOGUE, {"탭이름": "사건의 배경"}), ("공통 스토리", PROLOGUE, {"탭이름": "사건의 배경", "공개부분": [2]}),
    ])
    assert advance(client, host).status_code == 200
    view = state(client, host).json()
    assert tab(view, "공통 스토리") is None and tab(view, "사건의 배경")["내용"] == "둘째 부분"        # 같은 이름이면 새 탭 방식에서도 바뀐다


def test_profile_card_tab_name_and_append_mode(client, make_scripted_game):
    cards = [("캐릭터 선택", CHARACTER_SELECT, None), ("프로필 숙지", PROFILE, {"개인서사공개": {}}),
             ("프로필 숙지", PROFILE, {"개인서사공개": {"1": [2], "2": [2], "3": [2]}, "탭방식": "이어서"})]
    host, others, _, _ = make_scripted_game(cards)
    people = players_of(host, others)
    all_pick(client, people)
    assert advance(client, host).status_code == 200
    assert tab(state(client, people[0]).json(), "개인 서사") is not None
    assert advance(client, host).status_code == 200
    me = state(client, people[0]).json()
    assert tab(me, "개인 서사")["내용"].count("▶ 서사") == 2 and "2차 개인 서사" not in [t["이름"] for t in me["탭"]]   # 같은 탭에 이어 붙음
    cards[2] = ("프로필 숙지", PROFILE, {"개인서사공개": {"1": [2], "2": [2], "3": [2]}})
    host, others, _, _ = make_scripted_game(cards)
    people = players_of(host, others)
    all_pick(client, people)
    advance(client, host); advance(client, host)
    names = [t["이름"] for t in state(client, people[0]).json()["탭"]]
    assert "개인 서사" in names and "2차 개인 서사" in names                          # 기본은 새 탭


def test_custom_names_for_the_other_tab_cards(client, make_scripted_game):
    from app.default_phases import DISCUSSION, ENDING, INTRO, INVESTIGATE
    def setup(client_, host, wid):
        assert client_.patch(f"/api/works/{wid}/characters/1", headers=host.headers, json={"소개": "의사입니다."}).status_code == 200
    host, others, _, _ = make_scripted_game([
        ("자기소개", INTRO, {"탭이름": "인물 소개"}), ("조사", INVESTIGATE, {"탭이름": "얻은 단서"}),
        ("토론", DISCUSSION, {"내단서탭": "얻은 단서", "공개단서탭": "남이 보여 준 것"}), ("엔딩", ENDING, {"탭이름": "결말"}),
    ], setup=setup)
    names = lambda: [t["이름"] for t in state(client, host).json()["탭"]]
    assert "인물 소개" in names() and "자기소개" not in names()
    advance(client, host)
    assert "얻은 단서" in names() and "내 단서" not in names()
    advance(client, host)
    assert {"얻은 단서", "남이 보여 준 것"} <= set(names()) and "공개된 단서" not in names()
