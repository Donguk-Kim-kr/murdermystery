"""조사: 장소에 놓인 단서·증언 중 하나를 직접 골라 얻는다 (app/clues.py, 조사 단계의 결정, 사용자 2026-10-18)."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.default_phases import INVESTIGATE

from test_cards import answer, block, db, make_scripted_game, players_of, state, tab  # noqa: F401  (픽스처 포함)

# 단서 순서: 1 찢어진 편지(서재, 공개이름 서랍 속 종이) 2 깨진 안경(서재) 3 독이 든 컵(주방) / 증언 순서: 1 집사의 증언(주방, 공개이름 집사) 2 정원사의 증언(정원, 공개이름 정원사)
LETTER, GLASSES, CUP, BUTLER, GARDENER = "단서:1", "단서:2", "단서:3", "증언:1", "증언:2"


def build(client, host, wid):
    """저택(바깥) › 서재·주방, 정원. 서재: 단서 둘. 주방: 단서 하나와 증언 하나. 정원: 증언 하나. 연못: 아무것도 없다. 장소가 없는 단서도 하나."""
    url = f"/api/works/{wid}/content"
    def add(kind, **body):
        res = client.post(f"{url}/{kind}", headers=host.headers, json=body)
        assert res.status_code == 201, res.text
        return res.json()["순서"]
    mansion = add("places", 이름="저택")
    study = add("places", 이름="서재", 상위_장소_순서=mansion)
    kitchen = add("places", 이름="주방", 상위_장소_순서=mansion)
    garden = add("places", 이름="정원", 유형="야외")
    add("places", 이름="연못")
    add("clues", 이름="찢어진 편지", 공개이름="서랍 속 종이", 내용="편지 내용 XYZ1", 장소_순서=study)
    add("clues", 이름="깨진 안경", 내용="안경 내용 XYZ2", 장소_순서=study)
    add("clues", 이름="독이 든 컵", 내용="컵 내용 XYZ3", 장소_순서=kitchen)
    add("testimonies", 이름="집사의 증언", 공개이름="집사", 내용="증언 내용 XYZ4", 장소_순서=kitchen)
    add("testimonies", 이름="정원사의 증언", 공개이름="정원사", 내용="증언 내용 XYZ5", 장소_순서=garden)
    add("clues", 이름="장소 없는 단서", 내용="조사로는 얻지 못한다 XYZ6")


@pytest.fixture
def game(client, make_scripted_game):
    host, others, room, wid = make_scripted_game([("조사", INVESTIGATE, {"횟수": 2})], setup=build)
    people = players_of(host, others)
    qid = block(state(client, host).json(), "조사 대상")["질문ID"]
    return people, qid, room


def pick(client, who, qid, target):
    return answer(client, who, qid, target)


def newest(view):
    """방금 얻은 카드: 조사 결과 칸은 따로 없고, 얻은 것은 내 단서 탭의 맨 끝에 쌓인다."""
    return tab(view, "내 단서")["항목"][-1]


def items_of(client, who):
    return {i["값"]: i for i in block(state(client, who).json(), "조사 대상")["항목"]}


def notices(view):
    return [n["글"] for n in view["알림"]]


def test_items_are_listed_by_place_with_their_public_names(client, game):
    people, _, _ = game
    shown = items_of(client, people[0])
    assert list(shown) == [LETTER, GLASSES, CUP, BUTLER, GARDENER]                       # 장소 순서, 같은 장소에서는 단서가 먼저
    assert [(i["종류"], i["이름"], i["장소"]) for i in shown.values()] == [
        ("단서", "서랍 속 종이", "저택 › 서재"), ("단서", "깨진 안경", "저택 › 서재"), ("단서", "독이 든 컵", "저택 › 주방"),
        ("증언", "집사", "저택 › 주방"), ("증언", "정원사", "정원"),
    ]                                                                                      # 공개이름(없으면 이름), 진짜 이름은 아직 보이지 않는다
    assert "찢어진 편지" not in str(state(client, people[0]).json()["화면"]) and "XYZ" not in state(client, people[0]).text
    assert all(i["비활성"] is False and i["상태"] == "가능" for i in shown.values())
    assert "장소 없는 단서" not in str(shown)                                              # 장소가 없는 것은 조사로 얻지 못한다


def test_picking_an_item_gives_exactly_that_item_and_uses_a_count(client, game, db):
    people, qid, room = game
    res = pick(client, people[0], qid, CUP)                                                 # 서재의 단서가 아니라 주방의 컵을 직접 고른다
    assert res.status_code == 200
    view = res.json()
    got = newest(view)
    assert (got["이름"], got["공개이름"], got["내용"], got["장소"]) == ("독이 든 컵", "독이 든 컵", "컵 내용 XYZ3", "저택 › 주방")
    assert block(view, "조사 횟수")["완료"] == 1 and block(view, "조사 횟수")["전체"] == 2
    assert block(view, "조사 결과") is None
    assert notices(view) == ["'독이 든 컵'을 획득했습니다. '내 단서' 탭에서 확인하세요."]     # 획득한 순간의 알림
    rows = db.execute('SELECT 단서_순서, 증언_순서, 획득방법, 보유여부 FROM "획득" WHERE 진행_번호 = (SELECT 번호 FROM "진행" WHERE 방_번호 = %s)', (room["번호"],)).fetchall()
    assert rows == [(3, None, "조사", True)]


def test_the_notice_uses_the_public_name_and_the_tab_has_both_names(client, game):
    people, qid, _ = game
    view = pick(client, people[0], qid, LETTER).json()
    assert notices(view) == ["'서랍 속 종이'를 획득했습니다. '내 단서' 탭에서 확인하세요."]            # 알림에는 진짜 이름을 적지 않는다
    mine = newest(view)
    assert (mine["이름"], mine["공개이름"]) == ("찢어진 편지", "서랍 속 종이")             # 내 단서 탭에는 둘 다 있다


def test_a_clue_taken_by_someone_is_grey_for_everyone_else_and_for_the_owner(client, game):
    people, qid, _ = game
    pick(client, people[0], qid, LETTER)
    assert items_of(client, people[0])[LETTER]["상태"] == "얻음" and items_of(client, people[0])[LETTER]["비활성"] is True
    other = items_of(client, people[1])
    assert other[LETTER]["상태"] == "가져감" and other[LETTER]["비활성"] is True
    assert other[GLASSES]["비활성"] is False                                               # 같은 장소의 다른 단서는 그대로 고를 수 있다
    late = pick(client, people[1], qid, LETTER).json()                                     # 그래도 보내면 얻지 못하고 횟수도 쓰지 않는다
    assert tab(late, "내 단서")["항목"] == [] and block(late, "조사 횟수")["완료"] == 0
    assert notices(late) == []                                                             # 실패 알림은 없다(회색으로 이미 보인다)


def test_testimonies_are_gotten_once_by_each_player(client, game):
    people, qid, _ = game
    for who in people:
        got = newest(pick(client, who, qid, GARDENER).json())
        assert (got["이름"], got["공개이름"], got["내용"]) == ("정원사의 증언", "정원사", "증언 내용 XYZ5")
    assert items_of(client, people[0])[GARDENER]["상태"] == "얻음"                          # 내가 얻은 것만 회색이다
    assert items_of(client, people[0])[BUTLER]["비활성"] is False
    again = pick(client, people[0], qid, GARDENER).json()                                  # 이미 얻은 증언은 다시 얻을 수 없고 횟수도 쓰지 않는다
    assert block(again, "조사 횟수")["완료"] == 1


def test_a_player_can_still_pick_a_clue_in_a_place_where_only_their_own_remains(client, game):
    """남은 단서가 자기 것뿐인 장소는 그 장소에서 더 얻을 수 없지만, 다른 장소의 항목은 그대로 고를 수 있다."""
    people, qid, _ = game
    pick(client, people[0], qid, LETTER)
    pick(client, people[1], qid, GLASSES)
    shown = items_of(client, people[0])
    assert shown[LETTER]["비활성"] and shown[GLASSES]["비활성"]
    assert not shown[CUP]["비활성"] and not shown[BUTLER]["비활성"]


def test_count_limit_per_player(client, game):
    people, qid, _ = game
    pick(client, people[0], qid, LETTER)
    pick(client, people[0], qid, CUP)
    third = pick(client, people[0], qid, GARDENER).json()                                  # 횟수 2 를 모두 썼다
    assert notices(third)[-1] == "조사 횟수를 모두 사용했습니다."
    assert [c["이름"] for c in tab(third, "내 단서")["항목"]] == ["찢어진 편지", "독이 든 컵"]
    assert block(third, "조사 횟수")["완료"] == 2


@pytest.mark.parametrize("value", ["abc", 9999, None, [1], {"a": 1}, 1.5, True, -1, "단서:abc", "단서:99", "증언:0", "장소:1", "단서:6", ":", "단서:"])
def test_bad_values_do_not_break_the_card_or_use_a_count(client, game, value):
    people, qid, _ = game
    res = pick(client, people[0], qid, value)
    assert res.status_code == 200 and tab(res.json(), "내 단서")["항목"] == []
    assert state(client, people[0]).json()["오류"] == [] and state(client, people[1]).json()["오류"] == []
    assert newest(pick(client, people[0], qid, GARDENER).json())["이름"] == "정원사의 증언"   # 카드가 계속 동작한다
    assert block(state(client, people[0]).json(), "조사 횟수")["완료"] == 1


def test_simultaneous_picks_give_a_clue_to_exactly_one_player(client, game, db):
    people, qid, room = game
    with ThreadPoolExecutor(max_workers=3) as pool:
        codes = list(pool.map(lambda w: pick(client, w, qid, LETTER).status_code, people))
    assert codes == [200, 200, 200]
    got = [c["이름"] for who in people for c in (tab(state(client, who).json(), "내 단서") or {"항목": []})["항목"]]
    assert got == ["찢어진 편지"]                                                           # 한 사람만 얻는다
    rows = db.execute('SELECT count(*) FROM "획득" WHERE 진행_번호 = (SELECT 번호 FROM "진행" WHERE 방_번호 = %s)', (room["번호"],)).fetchone()
    assert rows == (1,)
    assert sorted(block(state(client, who).json(), "조사 횟수")["완료"] for who in people) == [0, 0, 1]   # 진 사람은 횟수를 쓰지 않는다


def test_clue_contents_reach_only_the_owner(client, game):
    people, qid, _ = game
    pick(client, people[0], qid, LETTER)
    assert "XYZ1" in state(client, people[0]).text
    for who in people[1:]:
        assert "XYZ1" not in state(client, who).text and "찢어진 편지" not in state(client, who).text   # 진짜 이름과 내용은 남에게 가지 않는다


def test_who_holds_what_is_shown_by_default_and_hidden_by_the_setting(client, make_scripted_game):
    for setting, shown in ((None, True), ({"조사공개": False}, False)):
        host, others, _, _ = make_scripted_game([("조사", INVESTIGATE, setting)], setup=build)
        people = players_of(host, others)
        qid = block(state(client, host).json(), "조사 대상")["질문ID"]
        pick(client, people[0], qid, LETTER)
        item = items_of(client, people[1])[LETTER]
        assert item["상태"] == "가져감"                                                      # 회색 표시는 설정과 상관없이 있다
        assert ("가진_사람" in item) is shown
        if shown:
            nick = next(p["닉네임"] for p in state(client, people[1]).json()["플레이어"] if p["계정_번호"] == people[0].number)
            assert item["가진_사람"] == [nick]
            assert items_of(client, people[0])[LETTER]["가진_사람"] == []                  # 내가 가진 것에는 나를 적지 않는다


def test_a_transferred_clue_stays_taken(client, make_scripted_game):
    from app.default_phases import DISCUSSION
    from test_game import advance

    host, others, _, _ = make_scripted_game([("조사", INVESTIGATE, None), ("토론", DISCUSSION, None)], setup=build)
    people = players_of(host, others)
    qid = block(state(client, host).json(), "조사 대상")["질문ID"]
    pick(client, people[0], qid, LETTER)
    assert advance(client, host).status_code == 200
    discussion = tab(state(client, people[0]).json(), "내 단서")
    handed = answer(client, people[0], discussion["질문ID"], {"동작": "양도", "단서": 1, "대상": [people[1].number]})
    assert handed.status_code == 200


def test_observer_sees_the_list_but_cannot_investigate_or_hold_clues(client, make_scripted_game):
    host, others, _, _ = make_scripted_game([("조사", INVESTIGATE, None)], players=2, observer_host=True, setup=build)
    view = state(client, host).json()
    choice = block(view, "조사 대상")
    assert all(i["비활성"] for i in choice["항목"])
    assert answer(client, host, choice["질문ID"], LETTER).status_code == 403
    assert tab(view, "내 단서") is None


def test_clues_stay_in_the_my_clues_tab_in_later_phases(client, make_scripted_game):
    from test_game import advance

    host, others, _, _ = make_scripted_game([("조사", INVESTIGATE, None), ("빈", "", None)], setup=build)
    choice = block(state(client, host).json(), "조사 대상")
    answer(client, host, choice["질문ID"], LETTER)
    assert advance(client, host).status_code == 200
    after = state(client, host).json()
    assert [c["이름"] for c in tab(after, "내 단서")["항목"]] == ["찢어진 편지"]
