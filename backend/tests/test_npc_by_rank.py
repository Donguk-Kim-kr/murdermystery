"""인원이 인물 수보다 적으면 제작자가 정한 순위대로 인물이 NPC 가 된다 (app/game.py npc_slots_for, 사용자 2026-10-18)."""
import pytest

from app.default_phases import CHARACTER_SELECT
from app.game import npc_slots_for
from test_cards import all_pick, answer, block, db, make_scripted_game, players_of, state  # noqa: F401  (픽스처 포함)


def rank(client_, host, wid, ranks):
    """인물 순서 → NPC 순위 를 정한다."""
    for slot, value in ranks.items():
        res = client_.patch(f"/api/works/{wid}/characters/{slot}", headers=host.headers, json={"NPC순위": value})
        assert res.status_code == 200, res.text


def chars(n, npc=(), ranks=None):
    ranks = ranks or {}
    return [{"순서": i, "NPC": i in npc, "NPC순위": ranks.get(i)} for i in range(1, n + 1)]


def test_the_lowest_ranks_become_npcs_for_the_missing_players():
    people = chars(8, ranks={3: 1, 5: 2})
    assert npc_slots_for(people, 8) == set()                      # 인원이 가득 차면 모두 플레이한다
    assert npc_slots_for(people, 7) == {3}                        # 7인: 순위 1
    assert npc_slots_for(people, 6) == {3, 5}                     # 6인: 순위 1, 2 둘 다
    ranked_first = chars(8, ranks={3: 2, 5: 1})
    assert npc_slots_for(ranked_first, 7) == {5}                  # 우선순위는 제작자가 정한 순위이다


def test_always_npc_characters_are_not_counted_and_the_range_is_enforced():
    people = chars(6, npc={6}, ranks={2: 1})                      # 6번은 시작부터 죽은 피해자
    assert npc_slots_for(people, 5) == set() and npc_slots_for(people, 4) == {2}
    with pytest.raises(ValueError, match="4명 이상 5명 이하"):
        npc_slots_for(people, 3)
    with pytest.raises(ValueError, match="4명 이상 5명 이하"):
        npc_slots_for(people, 6)
    with pytest.raises(ValueError, match="허용 인원\\(5명\\)"):
        npc_slots_for(chars(5), 4)                                # NPC 가 될 수 있는 인물이 없으면 인원이 정확히 같아야 한다


def test_a_game_with_fewer_players_leaves_the_ranked_character_out_of_the_selection(client, make_scripted_game):
    setup = lambda c, h, w: rank(c, h, w, {2: 1})
    host, others, _, _ = make_scripted_game([("캐릭터 선택", CHARACTER_SELECT, None)], players=3, characters=4, setup=setup)
    people = players_of(host, others)
    view = state(client, host).json()
    shown = [i["이름"] for i in block(view, "캐릭터 선택")["항목"]]
    assert shown == ["인물0", "인물2", "인물3"]                    # 순위 1(인물1)은 이 게임에서 NPC 라 고를 수 없다
    assert answer(client, people[0], block(view, "캐릭터 선택")["질문ID"], 2).status_code == 200   # 인물1(순서 2)은 받아들여지지 않는다
    assert state(client, people[0]).json()["나"]["인물_순서"] is None
    all_pick(client, people)
    assert all(state(client, p).json()["나"]["인물_순서"] is not None for p in people)


def test_a_full_game_lets_everyone_pick_the_ranked_character_too(client, make_scripted_game):
    setup = lambda c, h, w: rank(c, h, w, {2: 1})
    host, others, _, _ = make_scripted_game([("캐릭터 선택", CHARACTER_SELECT, None)], players=4, characters=4, setup=setup)
    shown = [i["이름"] for i in block(state(client, host).json(), "캐릭터 선택")["항목"]]
    assert shown == ["인물0", "인물1", "인물2", "인물3"]


def test_too_few_players_cannot_start_and_the_message_says_the_range(client, make_scripted_game):
    setup = lambda c, h, w: rank(c, h, w, {2: 1})
    with pytest.raises(AssertionError) as err:
        make_scripted_game([("캐릭터 선택", CHARACTER_SELECT, None)], players=2, characters=4, setup=setup)
    assert "3명 이상 4명 이하" in str(err.value)
