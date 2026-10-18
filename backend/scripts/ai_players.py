"""AI 플레이어를 방에 들여보내 게임을 시킨다.

사람이 방을 만들고(방장은 GM 관전으로 두면 모든 대화를 지켜보며 진행할 수 있다) 입장코드를 알려 주면, AI 계정을 만들어 그 코드로 입장시키고
게임이 시작되면 플레이한다. 단계 넘기기는 방장이 한다. 끝나면 Ctrl+C 로 멈춘다.

  docker compose exec app python backend/scripts/ai_players.py --code 1234 --count 4

* 모델 호출에는 ANTHROPIC_API_KEY 환경변수가 필요하다(도커는 프로젝트 폴더의 .env 에 적어 둔다). 키 없이 흐름만 보려면 `--brain simple`.
* 모델은 `--model` 또는 MM_AI_MODEL(기본 claude-opus-5-5), 생각 깊이는 `--effort` 또는 MM_AI_EFFORT(기본 low, 빠르다)로 바꾼다.
* 서버 주소는 `--url`(기본 http://localhost:8000).
"""
import argparse
import os
import secrets
import sys
import threading
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ai_players import Agent, ClaudeBrain, SimpleBrain  # noqa: E402

lock = threading.Lock()


def say(text: str) -> None:
    with lock:
        print(text, flush=True)


def make_account(http: httpx.Client, nickname: str) -> dict[str, str]:
    login_id = f"ai_{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(20)
    res = http.post("/api/auth/signup", json={"아이디": login_id, "패스워드": password, "닉네임": nickname})
    if res.status_code != 201:
        sys.exit(f"AI 계정을 만들지 못했습니다: {res.status_code} {res.text}")
    token = http.post("/api/auth/login", json={"아이디": login_id, "패스워드": password, "접속환경": "PC"}).json()["토큰"]
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    ap = argparse.ArgumentParser(description="AI 플레이어를 방에 입장시켜 게임을 시킨다")
    ap.add_argument("--code", required=True, help="방의 입장코드")
    ap.add_argument("--count", type=int, default=4, help="입장시킬 AI 수(기본 4)")
    ap.add_argument("--url", default=os.environ.get("MM_URL", "http://localhost:8000"))
    ap.add_argument("--brain", choices=["claude", "simple"], default="claude", help="claude: Anthropic API, simple: 모델 없이 규칙으로(시험용)")
    ap.add_argument("--model", default=os.environ.get("MM_AI_MODEL", "claude-opus-5-5"))
    ap.add_argument("--effort", default=os.environ.get("MM_AI_EFFORT", "low"), choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--nicknames", default="", help="쉼표로 구분한 AI 닉네임(기본 'AI 1, AI 2 …')")
    ap.add_argument("--think", type=float, default=4.0, help="AI 한 명이 모델을 부르는 최소 간격(초)")
    ap.add_argument("--verbose", action="store_true", help="AI 에게 준 상황 글도 출력")
    args = ap.parse_args()

    if args.brain == "claude" and not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY 가 없습니다. 프로젝트 폴더의 .env 에 ANTHROPIC_API_KEY=... 를 적고 docker compose up 을 다시 하거나, "
                 "모델 없이 흐름만 보려면 --brain simple 로 실행하세요.")
    names = [n.strip() for n in args.nicknames.split(",") if n.strip()] or [f"AI {i + 1}" for i in range(args.count)]
    names = (names + [f"AI {i + 1}" for i in range(len(names), args.count)])[: args.count]

    http = httpx.Client(base_url=args.url, timeout=60.0)
    agents: list[Agent] = []
    for name in names:
        headers = make_account(http, name)
        res = http.post("/api/rooms/join", headers=headers, json={"입장코드": args.code.strip().upper()})
        if res.status_code != 200:
            sys.exit(f"{name}: 입장하지 못했습니다 ({res.status_code} {res.json().get('detail') if res.headers.get('content-type', '').startswith('application/json') else res.text})")
        brain = ClaudeBrain(model=args.model, effort=args.effort, log=say) if args.brain == "claude" else SimpleBrain()
        agents.append(Agent(name, http, headers, brain, log=say, think_seconds=args.think, verbose=args.verbose))
        say(f"입장: {name}")
    say(f"AI {len(agents)}명이 입장했습니다(모델: {args.model if args.brain == 'claude' else '없음(simple)'}). 방장이 게임을 시작하면 플레이합니다. 멈추려면 Ctrl+C")

    stop = threading.Event()

    def loop(agent: Agent) -> None:
        while not stop.is_set():
            try:
                agent.tick()
            except Exception as err:                               # 한 명의 오류가 다른 AI 를 멈추지 않게 한다
                say(f"[{agent.nickname}] 오류: {type(err).__name__}: {err}")
            stop.wait(1.5)

    threads = [threading.Thread(target=loop, args=(a,), daemon=True) for a in agents]
    for t in threads:
        t.start()
    try:
        while not all(a.finished for a in agents):
            time.sleep(1)
        say("게임이 끝났습니다.")
    except KeyboardInterrupt:
        say("멈춥니다.")
    stop.set()


if __name__ == "__main__":
    main()
