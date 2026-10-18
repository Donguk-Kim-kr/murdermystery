"""AI 플레이어 러너 (app/ai_players.py): 모델 없이 SimpleBrain 으로 게임 흐름을 끝까지 돌리고, ClaudeBrain 의 요청 모양을 확인한다."""
from types import SimpleNamespace

from app.ai_players import RULES, TOOLS, Agent, ClaudeBrain, SimpleBrain, _json_after
from app.default_phases import CHARACTER_SELECT, INVESTIGATE, PROFILE, PROLOGUE

from test_cards import advance, block, db, make_scripted_game, players_of, state, tab  # noqa: F401  (픽스처 포함)
from test_investigation import build


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def agents_for(client, people, clock, seed=1):
    return [Agent(f"AI {i + 1}", client, who.headers, SimpleBrain(seed + i), log=lambda _t: None, clock=clock,
                  think_seconds=1, nudge_seconds=1, read_seconds=2) for i, who in enumerate(people)]


def run(agents, clock, rounds):
    for _ in range(rounds):
        clock.now += 3
        for a in agents:
            a.tick()


def game(client, make_scripted_game):
    cards = [("프롤로그", PROLOGUE, None), ("캐릭터 선택", CHARACTER_SELECT, None), ("프로필 숙지", PROFILE, None), ("조사", INVESTIGATE, {"횟수": 2})]
    host, others, room, wid = make_scripted_game(cards, players=4, setup=build)
    return players_of(host, others)


def test_agents_play_the_game_through_reading_choosing_and_investigating(client, make_scripted_game):
    people = game(client, make_scripted_game)
    host, clock = people[0], Clock()
    agents = agents_for(client, people, clock)

    run(agents, clock, 2)                                                           # 공통 스토리: 읽기 확인은 읽는 시간이 지난 뒤에 한다
    assert block(state(client, host).json(), "공통 스토리")["현황"] == {"완료": 4, "전체": 4}
    assert advance(client, host).status_code == 200

    run(agents, clock, 10)                                                          # 캐릭터 선택: 같은 인물을 고르려다 거절되면 다른 인물을 고른다
    assert all(state(client, p).json()["나"]["인물_순서"] is not None for p in people)
    assert len({state(client, p).json()["나"]["인물_순서"] for p in people}) == 4
    assert advance(client, host).status_code == 200

    run(agents, clock, 3)                                                           # 프로필 숙지
    assert block(state(client, host).json(), "개인 서사")["현황"] == {"완료": 4, "전체": 4}
    assert advance(client, host).status_code == 200

    run(agents, clock, 12)                                                          # 조사: 횟수(2)만큼 얻는다
    for p in people:
        assert len(tab(state(client, p).json(), "내 단서")["항목"]) >= 1
    chat = client.get("/api/game/me/chat", headers=host.headers).json()["메시지"]
    assert chat and all(m["장소"] == "전체" for m in chat)                            # SimpleBrain 이 전체에서 말했다


def test_prompt_has_rules_my_private_info_and_available_actions(client, make_scripted_game):
    people = game(client, make_scripted_game)
    host, clock = people[0], Clock()
    agents = agents_for(client, people, clock)
    run(agents, clock, 2)
    advance(client, host)
    run(agents, clock, 10)
    advance(client, host)
    run(agents, clock, 3)
    a = agents[0]
    view = state(client, host).json()
    chat = client.get("/api/game/me/chat", headers=host.headers).json()
    system, situation = a.prompt(view, chat, a._available(view), [])
    assert system.startswith(RULES[:30]) and "## 당신의 정보" in system
    assert "### 개인 서사" in system and "번의 서사 하나" in system                    # 내 개인 서사가 시스템 지시문에 있다
    assert "## 지금 상황" in situation and "3/4 프로필 숙지" in situation and "## 대화 (내 위치: 전체)" in situation
    assert _json_after(situation, "## 지금 할 수 있는 일") == a._available(view)


def test_each_agent_only_receives_what_its_own_account_can_see(client, make_scripted_game):
    people = game(client, make_scripted_game)
    host, clock = people[0], Clock()
    agents = agents_for(client, people, clock)
    run(agents, clock, 2)
    advance(client, host)
    run(agents, clock, 10)
    advance(client, host)
    run(agents, clock, 3)
    systems = []
    for a, who in zip(agents, people):
        view = state(client, who).json()
        chat = client.get("/api/game/me/chat", headers=who.headers).json()
        systems.append(a.prompt(view, chat, a._available(view), [])[0])
    texts = [[line for line in s.splitlines() if "번의 서사" in line] for s in systems]
    assert all(len(set(t)) >= 1 for t in texts)
    assert len({tuple(t) for t in texts}) == 4                                       # 서로 다른 개인 서사(남의 서사는 받지 못한다)


def fake_client(content=None, stop="tool_use", error=None):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if error:
            raise error
        return SimpleNamespace(stop_reason=stop, content=content or [])

    return SimpleNamespace(messages=SimpleNamespace(create=create)), calls


def test_claude_brain_sends_one_fresh_conversation_and_returns_tool_calls():
    content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text="..."),
               SimpleNamespace(type="tool_use", name="say", input={"text": "안녕하세요"}, id="t1")]
    client, calls = fake_client(content)
    brain = ClaudeBrain(model="claude-sonnet-5-5", effort="low", client=client)
    assert brain.decide("시스템", "상황") == [{"tool": "say", "input": {"text": "안녕하세요"}}]
    sent = calls[0]
    assert sent["model"] == "claude-sonnet-5-5" and sent["messages"] == [{"role": "user", "content": "상황"}]    # 이전 응답을 다시 보내지 않는다
    assert sent["system"][0]["text"] == "시스템" and sent["output_config"] == {"effort": "low"}
    assert [t["name"] for t in sent["tools"]] == [t["name"] for t in TOOLS] and "tool_choice" not in sent        # 강제 호출을 쓰지 않는다
    assert "temperature" not in sent and "thinking" not in sent


def test_claude_brain_never_stops_the_game_on_errors_or_refusals():
    logged = []
    client, _ = fake_client(error=RuntimeError("연결 끊김"))
    assert ClaudeBrain(client=client, log=logged.append).decide("s", "u") == [] and "RuntimeError" in logged[0]
    client, _ = fake_client(stop="refusal")
    assert ClaudeBrain(client=client).decide("s", "u") == []


def test_agent_ignores_unknown_question_ids_and_keeps_going(client, make_scripted_game):
    people = game(client, make_scripted_game)
    sent = []

    class Wild:
        def decide(self, system, situation):
            return [{"tool": "choose", "input": {"question_id": "없는:질문", "value": 1}},
                    {"tool": "say", "input": {"text": "x" * 800}}, {"tool": "wait", "input": {}}]

    clock = Clock()
    agent = Agent("AI", client, people[0].headers, Wild(), log=sent.append, clock=clock, think_seconds=0, nudge_seconds=0)
    clock.now = 10
    assert agent.tick() == "say"
    assert any("없는 질문ID" in m for m in agent.memory)
    chat = client.get("/api/game/me/chat", headers=people[0].headers).json()["메시지"]
    assert len(chat[-1]["내용"]) == 500                                              # 긴 말은 500자에서 자른다


def test_tool_schemas_use_only_plain_types():
    for tool in TOOLS:
        for prop in tool["input_schema"].get("properties", {}).values():
            assert isinstance(prop["type"], str), tool["name"]                          # 유니온 타입을 쓰지 않는다


def test_claude_brain_logs_why_no_action_was_chosen():
    logged = []
    client, calls = fake_client([SimpleNamespace(type="thinking", thinking="")], stop="max_tokens")
    assert ClaudeBrain(client=client, log=logged.append).decide("s", "u") == []
    assert "max_tokens" in logged[0] and calls[0]["max_tokens"] >= 4096                 # 생각에 쓰는 토큰까지 넉넉히


def test_choose_accepts_a_number_written_as_text_and_share_targets_as_text(client, make_scripted_game):
    people = game(client, make_scripted_game)
    host, clock = people[0], Clock()
    run(agents_for(client, people, clock), clock, 2)
    advance(client, host)                                                               # 캐릭터 선택
    slot = block(state(client, host).json(), "캐릭터 선택")["항목"][0]["값"]

    class AsText:
        def decide(self, system, situation):
            qid = _json_after(situation, "## 지금 할 수 있는 일")[0]["질문ID"]
            return [{"tool": "choose", "input": {"question_id": qid, "value": str(slot)}}]

    agent = Agent("AI", client, host.headers, AsText(), log=lambda _t: None, clock=clock, think_seconds=0, nudge_seconds=0)
    clock.now += 10
    assert agent.tick() == "choose"
    assert state(client, host).json()["나"]["인물_순서"] == slot                          # 글자로 온 값이 서버가 아는 숫자 값으로 바뀌어 받아들여졌다

    posted = []
    agent.http = SimpleNamespace(post=lambda path, headers=None, json=None: posted.append(json) or SimpleNamespace(status_code=200, json=lambda: {}))
    agent._act([{"tool": "share_clue", "input": {"question_id": "q", "clue": "3", "targets": "12, 15"}}],
               [{"질문ID": "q", "종류": "단서 보여주기"}], {"내_위치": "전체"})
    assert posted[0]["값"] == {"동작": "보여주기", "단서": 3, "대상": [12, 15]}


def test_claude_brain_backs_off_after_failures_and_explains_a_low_credit_balance():
    logged = []
    now = [0.0]
    client, calls = fake_client(error=RuntimeError("Your credit balance is too low to access the Anthropic API."))
    brain = ClaudeBrain(client=client, log=logged.append)
    brain.clock = lambda: now[0]
    assert brain.decide("s", "u") == [] and len(calls) == 1
    assert "Plans & Billing" in logged[0] and "5초" in logged[0]
    now[0] = 2.0
    assert brain.decide("s", "u") == [] and len(calls) == 1                           # 쉬는 동안에는 호출하지 않는다
    now[0] = 6.0
    brain.decide("s", "u")
    assert len(calls) == 2 and "10초" in logged[1]                                     # 계속 실패하면 쉬는 시간이 늘어난다


def test_claude_brain_tallies_token_usage_every_ten_calls():
    logged = []
    usage = SimpleNamespace(input_tokens=4000, output_tokens=300, cache_read_input_tokens=0)
    client, _ = fake_client([SimpleNamespace(type="tool_use", name="wait", input={}, id="t")])
    base = client.messages.create
    client.messages.create = lambda **kw: (lambda r: (setattr(r, "usage", usage), r)[1])(base(**kw))
    brain = ClaudeBrain(client=client, log=logged.append)
    for _ in range(10):
        brain.decide("s", "u")
    assert brain.usage == {"호출": 10, "입력": 40000, "출력": 3000, "캐시읽기": 0} and "사용량" in logged[-1]


def test_a_choice_the_card_refuses_is_reported_as_not_accepted_not_as_success(client, make_scripted_game):
    people = game(client, make_scripted_game)
    host, clock = people[0], Clock()
    run(agents_for(client, people, clock), clock, 2)
    advance(client, host)                                                               # 캐릭터 선택
    slot = block(state(client, host).json(), "캐릭터 선택")["항목"][0]["값"]
    logs = []

    class Same:
        def decide(self, system, situation):
            qid = _json_after(situation, "## 지금 할 수 있는 일")[0]["질문ID"]
            return [{"tool": "choose", "input": {"question_id": qid, "value": str(slot)}}]

    first = Agent("AI 1", client, people[0].headers, Same(), log=logs.append, clock=clock, think_seconds=0, nudge_seconds=0)
    second = Agent("AI 2", client, people[1].headers, Same(), log=logs.append, clock=clock, think_seconds=0, nudge_seconds=0)
    clock.now += 10
    assert first.tick() == "choose"
    # 둘째는 첫째가 고르기 전에 목록을 받아 같은 인물을 고른다(동시 선택): 서버는 선착순으로 한 명만 배정한다
    second.chat_after = 0
    qid = block(state(client, people[1]).json(), "캐릭터 선택")["질문ID"]
    assert second._answer(qid, slot, "'캐릭터 선택'에서 같은 인물 선택") is False
    assert "받아들여지지 않음" in logs[-1] and "이미 다른 사람이 고른 인물" in logs[-1]
    assert state(client, people[1]).json()["나"]["인물_순서"] is None
