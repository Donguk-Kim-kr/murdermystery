"""조사: 장소를 골라 단서·증언을 얻는다 (app/clues.py, 조사 단계의 결정)."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.default_phases import INVESTIGATE

from test_cards import answer, block, db, make_scripted_game, players_of, state, tab  # noqa: F401  (픽스처 포함)


def build(client, host, wid):
    """저택(바깥) › 서재·주방, 정원. 서재: 단서 둘. 주방: 단서 하나와 증언 하나. 정원: 증언 하나. 연못: 아무것도 없다."""
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
    add("clues", 이름="찢어진 편지", 내용="편지 내용 XYZ1", 장소_순서=study)
    add("clues", 이름="깨진 안경", 내용="안경 내용 XYZ2", 장소_순서=study)
    add("clues", 이름="독이 든 컵", 내용="컵 내용 XYZ3", 장소_순서=kitchen)
    add("testimonies", 화자="집사", 내용="증언 내용 XYZ4", 장소_순서=kitchen)
    add("testimonies", 화자="정원사", 내용="증언 내용 XYZ5", 장소_순서=garden)


@pytest.fixture
def game(client, make_scripted_game):
    host, others, room, wid = make_scripted_game([("조사", INVESTIGATE, {"횟수": 2})], setup=build)
    people = players_of(host, others)
    view = state(client, host).json()
    names = {i["이름"]: i["값"] for i in block(view, "조사할 장소")["항목"]}
    qid = block(view, "조사할 장소")["질문ID"]
    return people, names, qid, room


def pick(client, who, qid, place):
    return answer(client, who, qid, place)


def places_of(client, who):
    return {i["이름"]: i for i in block(state(client, who).json(), "조사할 장소")["항목"]}


def test_only_innermost_places_are_listed_with_their_path(client, game):
    people, names, _, _ = game
    assert sorted(names) == sorted(["저택 › 서재", "저택 › 주방", "정원", "연못"])
    shown = places_of(client, people[0])
    assert set(shown) == {"저택 › 서재", "저택 › 주방", "정원", "연못"}            # 바깥 장소(저택)는 조사 단위가 아니다
    assert shown["정원"]["유형"] == "야외"
    assert [s["비활성"] for s in (shown["저택 › 서재"], shown["저택 › 주방"], shown["정원"])] == [False, False, False]
    assert shown["연못"]["비활성"] is True                                            # 얻을 것이 없는 장소는 처음부터 비활성


def test_picking_a_place_gives_the_next_clue_and_uses_a_count(client, game, db):
    people, names, qid, room = game
    res = pick(client, people[0], qid, names["저택 › 서재"])
    assert res.status_code == 200
    view = res.json()
    assert block(view, "조사 결과")["내용"] == "찢어진 편지: 편지 내용 XYZ1"
    assert block(view, "조사 횟수")["완료"] == 1 and block(view, "조사 횟수")["전체"] == 2
    mine = tab(view, "내 단서")
    assert [c["이름"] for c in mine["항목"]] == ["찢어진 편지"] and mine["항목"][0]["장소"] == "저택 › 서재"
    rows = db.execute('SELECT 단서_순서, 증언_순서, 획득방법, 보유여부 FROM "획득" WHERE 진행_번호 = (SELECT 번호 FROM "진행" WHERE 방_번호 = %s)', (room["번호"],)).fetchall()
    assert rows == [(1, None, "조사", True)]


def test_a_clue_goes_to_one_player_only_and_the_next_picker_gets_the_next_one(client, game):
    people, names, qid, _ = game
    study = names["저택 › 서재"]
    assert block(pick(client, people[0], qid, study).json(), "조사 결과")["내용"].startswith("찢어진 편지")
    assert block(pick(client, people[1], qid, study).json(), "조사 결과")["내용"].startswith("깨진 안경")
    third = pick(client, people[2], qid, study).json()                                  # 단서가 모두 나갔다
    assert block(third, "조사 결과") is None
    assert [n["글"] for n in third["알림"]] == ["이 장소에서는 더 얻을 것이 없습니다."]
    assert block(third, "조사 횟수")["완료"] == 0                                         # 얻지 못하면 횟수를 쓰지 않는다
    for who in people:
        assert places_of(client, who)["저택 › 서재"]["비활성"] is True                   # 모두에게 비활성


def test_testimonies_are_gotten_once_by_each_player(client, game):
    people, names, qid, _ = game
    garden = names["정원"]
    for who in people:
        assert block(pick(client, who, qid, garden).json(), "조사 결과")["내용"] == "정원사의 증언: 증언 내용 XYZ5"
    again = pick(client, people[0], qid, garden).json()                  # 이미 얻은 증언은 다시 얻을 수 없고, 횟수도 쓰지 않는다
    assert [n["글"] for n in again["알림"]] == ["이 장소에서는 더 얻을 것이 없습니다."]
    assert block(again, "조사 횟수")["완료"] == 1
    assert places_of(client, people[0])["정원"]["비활성"] is True


def test_kitchen_gives_the_clue_before_the_testimony(client, game):
    people, names, qid, _ = game
    kitchen = names["저택 › 주방"]
    first = block(pick(client, people[0], qid, kitchen).json(), "조사 결과")["내용"]
    second = block(pick(client, people[1], qid, kitchen).json(), "조사 결과")["내용"]
    assert first.startswith("독이 든 컵") and second.startswith("집사의 증언")
    assert places_of(client, people[0])["저택 › 주방"]["비활성"] is False       # 이 사람은 아직 증언을 얻지 않았다
    assert places_of(client, people[1])["저택 › 주방"]["비활성"] is True


def test_count_limit_per_player(client, game):
    people, names, qid, _ = game
    pick(client, people[0], qid, names["저택 › 서재"])
    pick(client, people[0], qid, names["저택 › 주방"])
    third = pick(client, people[0], qid, names["정원"]).json()                            # 횟수 2 를 모두 썼다
    assert [n["글"] for n in third["알림"]][-1] == "조사 횟수를 모두 사용했습니다."
    assert [c["이름"] for c in tab(third, "내 단서")["항목"]] == ["찢어진 편지", "독이 든 컵"]
    assert block(third, "조사 횟수")["완료"] == 2


@pytest.mark.parametrize("value", ["abc", 9999, None, [1], {"a": 1}, 1.5, True, -1])
def test_bad_place_values_do_not_break_the_card_or_use_a_count(client, game, value):
    people, names, qid, _ = game
    res = pick(client, people[0], qid, value)
    assert res.status_code == 200 and block(res.json(), "조사 결과") is None
    assert state(client, people[0]).json()["오류"] == [] and state(client, people[1]).json()["오류"] == []
    assert block(pick(client, people[0], qid, names["정원"]).json(), "조사 결과") is not None   # 카드가 계속 동작한다
    assert block(state(client, people[0]).json(), "조사 횟수")["완료"] == 1


def test_places_that_are_not_innermost_cannot_be_investigated(client, game):
    people, _, qid, _ = game
    res = pick(client, people[0], qid, 1)                                                  # 저택(바깥 장소)
    assert block(res.json(), "조사 결과") is None


def test_simultaneous_picks_give_each_clue_to_exactly_one_player(client, game, db):
    people, names, qid, room = game
    study = names["저택 › 서재"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        codes = list(pool.map(lambda w: pick(client, w, qid, study).status_code, people))
    assert codes == [200, 200, 200]
    got = sorted(
        c["이름"] for who in people for c in (tab(state(client, who).json(), "내 단서") or {"항목": []})["항목"]
    )
    assert got == ["깨진 안경", "찢어진 편지"]                                              # 둘만 얻고, 같은 단서가 둘에게 가지 않는다
    rows = db.execute('SELECT count(*), count(DISTINCT 단서_순서) FROM "획득" WHERE 진행_번호 = (SELECT 번호 FROM "진행" WHERE 방_번호 = %s)', (room["번호"],)).fetchone()
    assert rows == (2, 2)


def test_clue_contents_reach_only_the_owner(client, game):
    people, names, qid, _ = game
    pick(client, people[0], qid, names["저택 › 서재"])
    assert "XYZ1" in state(client, people[0]).text
    for who in people[1:]:
        assert "XYZ1" not in state(client, who).text and "찢어진 편지" not in state(client, who).text


def test_observer_sees_places_but_cannot_investigate_or_hold_clues(client, make_scripted_game):
    host, others, _, _ = make_scripted_game([("조사", INVESTIGATE, None)], players=2, observer_host=True, setup=build)
    view = state(client, host).json()
    choice = block(view, "조사할 장소")
    assert all(i["비활성"] for i in choice["항목"])
    assert answer(client, host, choice["질문ID"], choice["항목"][0]["값"]).status_code == 403
    assert tab(view, "내 단서") is None


def test_clues_stay_in_the_my_clues_tab_in_later_phases(client, make_scripted_game):
    from test_game import advance

    host, others, _, _ = make_scripted_game([("조사", INVESTIGATE, None), ("빈", "", None)], setup=build)
    view = state(client, host).json()
    choice = block(view, "조사할 장소")
    study = next(i["값"] for i in choice["항목"] if i["이름"].endswith("서재"))
    answer(client, host, choice["질문ID"], study)
    assert advance(client, host).status_code == 200
    after = state(client, host).json()
    assert [c["이름"] for c in tab(after, "내 단서")["항목"]] == ["찢어진 편지"]
