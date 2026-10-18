"""자동으로 넘기기: 시간이 끝났을 때뿐 아니라 모두가 해야 할 일(읽기 확인·인물 고르기·투표)을 모두 끝냈을 때도 넘어간다 (app/engine.py auto_advance_if_due)."""
from app.default_phases import CHARACTER_SELECT, FINAL_VOTE, INVESTIGATE, PROLOGUE
from app.main import tick_games

from test_cards import all_pick, answer, block, db, make_scripted_game, players_of, state  # noqa: F401  (픽스처 포함)
from test_game import advance, pause


def auto(client, host, on=True):
    res = client.post("/api/game/me/settings", headers=host.headers, json={"자동_진행": on})
    assert res.status_code == 200, res.text


def where(client, who):
    return state(client, who).json()["페이즈"]["위치"]


def test_everyone_confirming_the_read_moves_on_without_waiting_for_the_time(client, make_scripted_game):
    host, others, _, _ = make_scripted_game([("프롤로그", PROLOGUE, None), ("다음", INVESTIGATE, None)])
    people = players_of(host, others)
    auto(client, host)
    qid = block(state(client, host).json(), "공통 스토리")["질문ID"]
    for who in people[:-1]:
        assert answer(client, who, qid).status_code == 200
    tick_games(client.app)
    assert where(client, host) == 1                                                  # 한 명이 아직 확인하지 않았다
    assert answer(client, people[-1], qid).status_code == 200
    tick_games(client.app)
    assert where(client, host) == 2                                                  # 모두 확인했으니 넘어간다(시간은 아직 남아 있다)


def test_everyone_choosing_a_character_moves_on(client, make_scripted_game):
    host, others, _, _ = make_scripted_game([("캐릭터 선택", CHARACTER_SELECT, None), ("다음", INVESTIGATE, None)])
    people = players_of(host, others)
    auto(client, host)
    all_pick(client, people[:-1])
    tick_games(client.app)
    assert where(client, host) == 1
    view = state(client, people[-1]).json()                                          # 마지막 사람이 남은 인물을 고른다
    free = next(i for i in block(view, "캐릭터 선택")["항목"] if i["선택한_계정"] is None)
    assert answer(client, people[-1], block(view, "캐릭터 선택")["질문ID"], free["값"]).status_code == 200
    tick_games(client.app)
    assert where(client, host) == 2


def test_everyone_voting_moves_on_and_a_tie_does_not(client, make_scripted_game):
    host, others, _, _ = make_scripted_game([("캐릭터 선택", CHARACTER_SELECT, None), ("최종 투표", FINAL_VOTE, None), ("다음", INVESTIGATE, None)])
    people = players_of(host, others)
    all_pick(client, people)
    assert advance(client, host).status_code == 200
    auto(client, host)
    slots = {who.number: state(client, who).json()["나"]["인물_순서"] for who in people}
    order = [slots[p.number] for p in people]
    qid = block(state(client, host).json(), "최종 투표")["질문ID"]
    # 서로 한 표씩(동률) → 모두 투표했지만 재투표가 되어 넘어가지 않는다
    for i, who in enumerate(people):
        assert answer(client, who, qid, order[(i + 1) % len(people)]).status_code == 200
    tick_games(client.app)
    assert where(client, host) == 2
    assert block(state(client, host).json(), "최종 투표")["투표수"] == 0                # 동률이라 투표가 지워졌다
    for who in people:                                                               # 이번에는 한 명(0번)에게 몰아서 투표
        target = order[0] if slots[who.number] != order[0] else order[1]
        assert answer(client, who, block(state(client, who).json(), "최종 투표")["질문ID"], target).status_code == 200
    tick_games(client.app)
    assert where(client, host) == 3


def test_a_phase_with_nothing_to_finish_waits_for_the_time_and_paused_or_off_never_moves(client, make_scripted_game):
    host, others, _, _ = make_scripted_game([("프롤로그", PROLOGUE, None), ("조사", INVESTIGATE, None), ("끝", INVESTIGATE, None)])
    people = players_of(host, others)
    qid = block(state(client, host).json(), "공통 스토리")["질문ID"]
    for who in people:
        answer(client, who, qid)
    tick_games(client.app)
    assert where(client, host) == 1                                                  # 자동 진행을 켜지 않았으면 넘어가지 않는다
    auto(client, host)
    assert pause(client, host, True).status_code == 200
    tick_games(client.app)
    assert where(client, host) == 1                                                  # 일시정지 중에는 넘어가지 않는다
    assert pause(client, host, False).status_code == 200
    tick_games(client.app)
    assert where(client, host) == 2
    tick_games(client.app)
    assert where(client, host) == 2                                                  # 조사 단계는 모두 끝냈다고 볼 것이 없어서 시간이 끝나기를 기다린다
