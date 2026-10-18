"""캐릭터 선택: 확인한 뒤에도 다음 단계로 넘어가기 전까지 취소할 수 있고, 선택 화면 소개를 보일 수 있다 (사용자 2026-10-18)."""
from app.default_phases import CHARACTER_SELECT
from test_cards import advance, all_pick, answer, block, db, make_scripted_game, players_of, pick, state, tab  # noqa: F401  (픽스처 포함)


def selecting(client, make_scripted_game, settings=None, setup=None, **kw):
    host, others, _, _ = make_scripted_game([("캐릭터 선택", CHARACTER_SELECT, settings), ("다음", "", None)], setup=setup, **kw)
    return host, players_of(host, others)


def qid(client, who):
    return block(state(client, who).json(), "캐릭터 선택")["질문ID"]


def test_a_confirmed_pick_can_be_cancelled_and_then_taken_by_someone_else(client, make_scripted_game):
    host, people = selecting(client, make_scripted_game)
    assert pick(client, people[0], 1).status_code == 200
    mine = state(client, people[0]).json()
    assert mine["나"]["인물_순서"] == 1 and block(mine, "캐릭터 선택")["내_선택_끝남"] is True
    assert block(mine, "선택 완료")["완료"] == 1
    assert pick(client, people[1], 1).status_code == 200                                       # 이미 골라진 인물은 받지 않는다
    assert state(client, people[1]).json()["나"]["인물_순서"] is None
    assert answer(client, people[0], qid(client, people[0]), "취소").status_code == 200       # 취소
    after = state(client, people[0]).json()
    assert after["나"]["인물_순서"] is None and block(after, "캐릭터 선택")["내_선택_끝남"] is False
    assert block(after, "선택 완료")["완료"] == 0
    assert pick(client, people[1], 1).status_code == 200                                       # 풀린 인물은 다른 사람이 고를 수 있다
    assert state(client, people[1]).json()["나"]["인물_순서"] == 1
    assert pick(client, people[0], 2).status_code == 200 and state(client, people[0]).json()["나"]["인물_순서"] == 2


def test_cancelling_with_nothing_picked_changes_nothing(client, make_scripted_game):
    host, people = selecting(client, make_scripted_game)
    assert answer(client, people[0], qid(client, people[0]), "취소").status_code == 200
    assert state(client, people[0]).json()["나"]["인물_순서"] is None


def test_the_pick_is_saved_and_cleared_in_the_database(client, make_scripted_game, db):
    host, people = selecting(client, make_scripted_game)
    pick(client, people[0], 1)
    rows = lambda: db.execute('SELECT 인물_순서 FROM "참여" WHERE 진행_번호 = (SELECT max(번호) FROM "진행") ORDER BY 계정_번호').fetchall()
    assert (1,) in rows()
    answer(client, people[0], qid(client, people[0]), "취소")
    assert (1,) not in rows()


def test_it_cannot_be_cancelled_once_the_next_phase_has_started(client, make_scripted_game):
    host, people = selecting(client, make_scripted_game)
    all_pick(client, people)
    old = qid(client, people[0])
    assert advance(client, host).status_code == 200
    assert answer(client, people[0], old, "취소").status_code != 200                         # 지금은 받지 않는 질문이다
    assert state(client, people[0]).json()["나"]["인물_순서"] is not None


def test_pick_intro_is_shown_only_when_the_card_setting_asks(client, make_scripted_game):
    def setup(client_, host, wid):
        assert client_.patch(f"/api/works/{wid}/characters/1", headers=host.headers, json={"선택소개": "마을 의사. 다정하다."}).status_code == 200
        assert client_.patch(f"/api/works/{wid}/characters/1", headers=host.headers, json={"소개": "자기소개 멘트(여기엔 안 나온다)"}).status_code == 200
    host, people = selecting(client, make_scripted_game, setup=setup)
    items = block(state(client, host).json(), "캐릭터 선택")["항목"]
    assert all("선택소개" not in i for i in items)
    host, people = selecting(client, make_scripted_game, {"소개보이기": True}, setup)
    items = {i["값"]: i for i in block(state(client, host).json(), "캐릭터 선택")["항목"]}
    assert items[1]["선택소개"] == "마을 의사. 다정하다." and items[2]["선택소개"] is None
    assert "자기소개 멘트" not in str(state(client, host).json())


def test_character_description_tab_lists_everyone_and_who_plays_whom(client, make_scripted_game):
    def setup(client_, host, wid):
        assert client_.patch(f"/api/works/{wid}/characters/1", headers=host.headers, json={"나이": 34, "성별": "남", "선택소개": "다정한 의사"}).status_code == 200
        assert client_.patch(f"/api/works/{wid}/characters/4", headers=host.headers, json={"NPC": True, "직업": "정원사"}).status_code == 200
    host, people = selecting(client, make_scripted_game, setup=setup, characters=4)
    shown = tab(state(client, host).json(), "캐릭터 설명")["내용"]
    assert "인물0 (의사, 34세, 남)" in shown and "인물1 (의사)" in shown and "인물3 (정원사) [NPC]" in shown
    assert "다정한 의사" not in shown                                         # 소개는 카드 설정이 켜졌을 때만
    assert pick(client, people[0], 1).status_code == 200
    mine = tab(state(client, people[1]).json(), "캐릭터 설명")["내용"]         # 다른 사람의 화면에도 누가 맡았는지가 보인다
    assert "인물0 (의사, 34세, 남) - " in mine
    answer(client, people[0], qid(client, people[0]), "취소")
    assert "인물0 (의사, 34세, 남) - " not in tab(state(client, people[1]).json(), "캐릭터 설명")["내용"]
    host2, people2 = selecting(client, make_scripted_game, {"소개보이기": True}, setup, characters=4)
    assert "다정한 의사" in tab(state(client, host2).json(), "캐릭터 설명")["내용"]
    host3, people3 = selecting(client, make_scripted_game, {"설명탭": False}, setup, characters=4)
    assert tab(state(client, host3).json(), "캐릭터 설명") is None
    host4, people4 = selecting(client, make_scripted_game, {"설명탭이름": "등장인물"}, setup, characters=4)
    assert tab(state(client, host4).json(), "등장인물") is not None
