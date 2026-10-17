"""게임 진행 엔진의 상태 (docs/ENGINE_SPEC.md, docs/ENGINE_DESIGN.md 1-8·1-9).

게임이 시작되면 방마다 `Game` 이 하나 생긴다. 진행 중인 상태(현재 페이즈, 누가 어떤 인물인지, 상태 버전 등)는
서버 메모리에 두고, 기록으로 남아야 하는 것(진행, 참여, 인물 배정)은 DB 에 쓴다. 서버를 다시 시작하면 진행 중이던 게임은
이어지지 않는다(기존 결정: 서버 재시작은 지금 고려하지 않는다). 서버는 프로세스 하나로만 실행한다.

확정 스냅샷(`버전.시나리오`)을 게임이 시작될 때 한 번 읽어 와서 `snapshot` 에 들고 있는다. 이후 제작용 콘텐츠가 바뀌어도
진행 중인 게임은 영향을 받지 않는다.
"""
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Player:
    account_id: int
    nickname: str
    character: int | None = None   # 인물 순서. 캐릭터 선택에서 확인한 뒤에 정해진다


@dataclass
class Observer:
    account_id: int
    nickname: str


@dataclass
class Game:
    id: int                          # 진행 번호
    room_id: int
    work_id: int
    version: str
    host_id: int
    snapshot: dict[str, Any]
    players: dict[int, Player]       # 계정 번호 → 플레이어. 입장한 순서를 지킨다(dict 는 넣은 순서를 기억한다)
    observers: dict[int, Observer] = field(default_factory=dict)
    phase_index: int = 0             # 흐름 안의 위치(0부터)
    state_version: int = 1           # 상태가 바뀔 때마다 올라간다(화면이 오래된 응답을 거르는 데 쓴다)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    @property
    def phases(self) -> list[dict[str, Any]]:
        return sorted(self.snapshot.get("진행순서") or [], key=lambda p: p["순서"])

    @property
    def phase(self) -> dict[str, Any]:
        return self.phases[self.phase_index]

    def bump(self) -> int:
        self.state_version += 1
        return self.state_version


class GameRegistry:
    """진행 중인 게임을 방 번호로 찾는다."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._games: dict[int, Game] = {}

    def add(self, game: Game) -> None:
        with self._lock:
            self._games[game.room_id] = game

    def get(self, room_id: int) -> Game | None:
        with self._lock:
            return self._games.get(room_id)

    def of_account(self, account_id: int) -> Game | None:
        with self._lock:
            for game in self._games.values():
                if account_id in game.players or account_id in game.observers:
                    return game
            return None

    def remove(self, room_id: int) -> None:
        with self._lock:
            self._games.pop(room_id, None)
