"""대기실의 "AI 추가"(app/ai_room.py, app/ai_runner.py): 방장만, 켜져 있을 때만, 자리가 있을 때만, 방이 닫히면 멈춘다."""
import pytest

from app.ai_runner import AiRunner
from app.config import get_settings


class FakeProc:
    def __init__(self):
        self.stopped = False

    def poll(self):
        return 0 if self.stopped else None

    def terminate(self):
        self.stopped = True


@pytest.fixture
def ai(client, monkeypatch):
    """AI 추가를 켜고, 실제 프로세스 대신 가짜를 띄우게 한다. 호출 기록(주소·입장코드·닉네임·종류)과 가짜 프로세스를 돌려준다."""
    monkeypatch.setenv("MM_AI_ENABLED", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    calls, procs = [], []

    def launch(url, code, nickname, brain):
        calls.append((url, code, nickname, brain))
        procs.append(FakeProc())
        return procs[-1]

    original = client.app.state.ai_runner
    client.app.state.ai_runner = AiRunner("http://127.0.0.1:8000", 12, launch)          # 시험마다 새로(client 는 모듈 안에서 함께 쓴다)
    yield calls, procs
    client.app.state.ai_runner = original
    get_settings.cache_clear()


def make_room(client, make_account, confirm, players=3):
    owner = make_account()
    wid = client.post("/api/works", headers=owner.headers, json={"제목": "AI 시험"}).json()["번호"]
    for i in range(players):
        client.post(f"/api/works/{wid}/characters", headers=owner.headers, json={"이름": f"p{i}"})
    confirm(wid)
    room = client.post("/api/rooms", headers=owner.headers, json={"작품_번호": wid}).json()
    return owner, room


def add(client, who, **body):
    return client.post("/api/rooms/me/ai", headers=who.headers, json=body)


def test_status_shows_whether_it_is_allowed_and_whether_a_model_key_exists(client, make_account, monkeypatch):
    who = make_account()
    assert client.get("/api/ai/status").status_code == 401
    off = client.get("/api/ai/status", headers=who.headers).json()
    assert off["사용가능"] is False and off["모델사용가능"] is False
    monkeypatch.setenv("MM_AI_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    get_settings.cache_clear()
    try:
        on = client.get("/api/ai/status", headers=who.headers).json()
        assert on["사용가능"] is True and on["모델사용가능"] is True and on["모델"]
    finally:
        get_settings.cache_clear()


def test_refused_when_the_server_does_not_allow_it(client, make_account, confirm):
    owner, _ = make_room(client, make_account, confirm)
    assert add(client, owner, 방식="simple").status_code == 403


def test_host_adds_ai_one_at_a_time_with_numbered_nicknames(client, make_account, confirm, ai):
    calls, _ = ai
    owner, room = make_room(client, make_account, confirm, players=4)
    first, second = add(client, owner, 방식="simple"), add(client, owner, 방식="simple")
    assert first.status_code == 202 and first.json() == {"닉네임": "AI 1", "방식": "simple"}
    assert second.json()["닉네임"] == "AI 2"
    assert [(c[1], c[2], c[3]) for c in calls] == [(room["입장코드"], "AI 1", "simple"), (room["입장코드"], "AI 2", "simple")]
    assert all(c[0].startswith("http://127.0.0.1:") for c in calls)           # 서버 자신의 주소로 입장한다


def test_only_the_host_can_add_and_only_while_waiting(client, make_account, confirm, ai, test_dbname):
    import psycopg

    owner, room = make_room(client, make_account, confirm)
    guest = make_account()
    assert client.post("/api/rooms/join", headers=guest.headers, json={"입장코드": room["입장코드"]}).status_code == 200
    assert add(client, guest, 방식="simple").status_code == 403
    assert add(client, make_account(), 방식="simple").status_code == 404           # 방이 없는 사람
    with psycopg.connect(f"dbname={test_dbname}", autocommit=True) as conn:
        conn.execute('UPDATE "방" SET "상태" = \'진행\' WHERE "번호" = %s', (room["번호"],))
    assert add(client, owner, 방식="simple").status_code == 409


def test_seats_are_counted_including_ai_that_has_not_joined_yet(client, make_account, confirm, ai):
    owner, _ = make_room(client, make_account, confirm, players=2)                  # 최대 2명, 방장이 한 자리
    assert add(client, owner, 방식="simple").status_code == 202
    full = add(client, owner, 방식="simple")
    assert full.status_code == 409 and "가득" in full.json()["detail"]


def test_model_ai_needs_the_server_key_and_the_default_follows_the_key(client, make_account, confirm, ai, monkeypatch):
    calls, _ = ai
    owner, _ = make_room(client, make_account, confirm, players=4)
    refused = add(client, owner, 방식="claude")
    assert refused.status_code == 409 and "ANTHROPIC_API_KEY" in refused.json()["detail"]
    assert add(client, owner).json()["방식"] == "simple"                           # 키가 없으면 기본은 간단한 AI
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert add(client, owner).json()["방식"] == "claude"
    assert all("sk-test" not in " ".join(map(str, c)) for c in calls)              # 키는 인자로 넘기지 않는다(환경변수로만)


def test_closing_the_room_stops_its_ai(client, make_account, confirm, ai):
    _, procs = ai
    owner, _ = make_room(client, make_account, confirm, players=4)
    add(client, owner, 방식="simple")
    add(client, owner, 방식="simple")
    assert [p.stopped for p in procs] == [False, False]
    assert client.post("/api/rooms/leave", headers=owner.headers).status_code == 204     # 방장이 나가면 방이 닫힌다
    assert [p.stopped for p in procs] == [True, True]


def test_global_process_limit(client, make_account, confirm, ai):
    client.app.state.ai_runner.max_processes = 1
    owner, _ = make_room(client, make_account, confirm, players=4)
    assert add(client, owner, 방식="simple").status_code == 202
    assert add(client, owner, 방식="simple").status_code == 503
