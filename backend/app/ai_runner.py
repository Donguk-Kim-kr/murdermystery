"""방장이 대기실에서 "AI 추가"를 눌렀을 때 AI 플레이어를 띄우는 부분 (사용자 요청 2026-10-21).

AI 는 서버 안에서 돌지 않는다. 전에 터미널에서 실행하던 러너(`scripts/ai_players.py`)를 **자식 프로세스**로 띄워서, 그 러너가 일반 계정을 만들어
입장코드로 들어오고 사람과 같은 API 로 플레이한다(정보 격리와 규칙 검사는 서버가 그대로 한다). 버튼 한 번에 AI 한 명(프로세스 하나)이다.

* 모델을 쓰는 AI(`claude`)의 비용은 서버의 ANTHROPIC_API_KEY 로 나간다. 키는 명령줄에 싣지 않고 환경변수로만 물려준다.
* 방이 닫히거나 서버가 꺼지면 그 방의 AI 프로세스를 멈춘다. 게임이 끝나면 러너가 스스로 끝난다.
* 프로세스를 띄우는 방법(`launch`)은 시험에서 바꿀 수 있다.
"""
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ai_players.py"
BRAINS = ("claude", "simple")


@dataclass
class AiEntry:
    nickname: str
    brain: str
    proc: "subprocess.Popen"
    started: float = field(default_factory=time.monotonic)

    def alive(self) -> bool:
        return self.proc.poll() is None


def launch_runner(url: str, code: str, nickname: str, brain: str) -> "subprocess.Popen":
    """러너를 자식 프로세스로 띄운다. 인자는 서버가 정한 값(입장코드·닉네임·종류)뿐이고 사용자가 쓴 글은 들어가지 않는다."""
    cmd = [sys.executable, str(SCRIPT), "--code", code, "--count", "1", "--nicknames", nickname, "--brain", brain, "--url", url]
    return subprocess.Popen(cmd, env=os.environ.copy())          # 출력은 서버 로그로 나온다


class AiRunner:
    def __init__(self, url: str, max_processes: int, launch: Callable[[str, str, str, str], "subprocess.Popen"] = launch_runner):
        self.url, self.max_processes, self.launch = url, max_processes, launch
        self._rooms: dict[int, list[AiEntry]] = {}
        self._lock = threading.Lock()

    def _prune(self) -> None:
        for room_id in list(self._rooms):
            self._rooms[room_id] = [e for e in self._rooms[room_id] if e.alive()]
            if not self._rooms[room_id]:
                del self._rooms[room_id]

    def running(self) -> int:
        with self._lock:
            self._prune()
            return sum(len(v) for v in self._rooms.values())

    def pending(self, room_id: int, member_nicknames: set[str]) -> int:
        """띄웠지만 아직 방에 들어오지 못한 AI 수(자리를 이미 잡은 것으로 센다)."""
        with self._lock:
            self._prune()
            return sum(1 for e in self._rooms.get(room_id, []) if e.nickname not in member_nicknames)

    def next_nickname(self, room_id: int, taken: set[str]) -> str:
        with self._lock:
            self._prune()
            used = taken | {e.nickname for e in self._rooms.get(room_id, [])}
            number = 1
            while f"AI {number}" in used:
                number += 1
            return f"AI {number}"

    def spawn(self, room_id: int, code: str, nickname: str, brain: str) -> AiEntry:
        if brain not in BRAINS:
            raise ValueError(f"알 수 없는 AI 종류입니다: {brain}")
        with self._lock:
            self._prune()
            if sum(len(v) for v in self._rooms.values()) >= self.max_processes:
                raise RuntimeError("서버가 동시에 돌릴 수 있는 AI 수를 넘었습니다")
            entry = AiEntry(nickname, brain, self.launch(self.url, code, nickname, brain))
            self._rooms.setdefault(room_id, []).append(entry)
            return entry

    def stop_room(self, room_id: int) -> None:
        with self._lock:
            entries = self._rooms.pop(room_id, [])
        for e in entries:
            if e.alive():
                e.proc.terminate()

    def stop_all(self) -> None:
        for room_id in list(self._rooms):
            self.stop_room(room_id)
