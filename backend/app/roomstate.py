"""대기실의 메모리 상태 (docs/DB_RULES.md B38).

방(`방` 행)은 DB 에 남지만, 게임 시작 전에 누가 들어와 있는지는 DB 에 기록하지 않는다(사용자 결정). 이 상태는 서버 프로세스
메모리에만 있으므로 서버를 다시 시작하면 사라지고, 입장했던 사람은 입장코드로 다시 들어와야 한다(방장은 DB 로 복원된다).
서버를 여러 프로세스로 띄우면 프로세스마다 상태가 갈라지므로 **한 프로세스로만 실행**해야 한다.

* 한 계정은 한 번에 한 방에만 있을 수 있다 (사용자 결정).
* 폴링이 `member_timeout` 초 끊기면 방에서 나간 것으로 본다. 방장은 방 소유자라서 끊겨도 자리에서 빠지지 않는다.
* 방장은 플레이어로 참여할지 선택한다. 참여하지 않는 방장은 인원 수에 포함되지 않는다.
"""
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Callable


class RoomError(Exception):
    """대기실 규칙 위반. `code` 로 API 계층이 상태 코드를 정한다."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class Member:
    account_id: int
    nickname: str
    playing: bool
    last_seen: float


@dataclass
class WaitingRoom:
    room_id: int
    code: str
    host_id: int
    members: dict[int, Member] = field(default_factory=dict)

    def player_count(self) -> int:
        return sum(1 for m in self.members.values() if m.playing)


class RoomRegistry:
    def __init__(self, member_timeout: float, clock: Callable[[], float] = time.monotonic):
        self.member_timeout = member_timeout
        self.clock = clock  # 테스트에서 시간을 흘려 보내기 위해 바꿀 수 있다
        self._lock = threading.RLock()
        self._rooms: dict[int, WaitingRoom] = {}
        self._room_of: dict[int, int] = {}  # 계정 번호 → 방 번호

    # ---- 조회 -------------------------------------------------------------------------
    def room_of(self, account_id: int) -> WaitingRoom | None:
        with self._lock:
            self._prune()
            rid = self._room_of.get(account_id)
            return self._rooms.get(rid) if rid is not None else None

    def get(self, room_id: int) -> WaitingRoom | None:
        with self._lock:
            self._prune()
            return self._rooms.get(room_id)

    def room_ids(self) -> list[int]:
        with self._lock:
            return list(self._rooms)

    # ---- 변경 -------------------------------------------------------------------------
    def open_room(self, room_id: int, code: str, host_id: int, nickname: str, playing: bool) -> WaitingRoom:
        """방장이 방을 연다(또는 서버 재시작 뒤 DB 의 방을 복원한다)."""
        with self._lock:
            self._prune()
            if host_id in self._room_of and self._room_of[host_id] != room_id:
                raise RoomError("in_other_room", "이미 다른 방에 참여 중입니다")
            room = self._rooms.get(room_id) or WaitingRoom(room_id, code, host_id)
            self._rooms[room_id] = room
            room.members[host_id] = Member(host_id, nickname, playing, self.clock())
            self._room_of[host_id] = room_id
            return room

    def join(self, room_id: int, account_id: int, nickname: str, capacity: int) -> WaitingRoom:
        with self._lock:
            self._prune()
            room = self._rooms.get(room_id)
            if room is None:
                raise RoomError("closed", "방을 찾을 수 없습니다")
            if account_id in room.members:  # 이미 이 방에 있다: 그대로 둔다
                room.members[account_id].last_seen = self.clock()
                return room
            if account_id in self._room_of:
                raise RoomError("in_other_room", "이미 다른 방에 참여 중입니다. 먼저 나가 주세요")
            if room.player_count() >= capacity:
                raise RoomError("full", "방이 가득 찼습니다")
            room.members[account_id] = Member(account_id, nickname, True, self.clock())
            self._room_of[account_id] = room_id
            return room

    def touch(self, account_id: int) -> None:
        with self._lock:
            rid = self._room_of.get(account_id)
            room = self._rooms.get(rid) if rid is not None else None
            if room and account_id in room.members:
                room.members[account_id].last_seen = self.clock()

    def leave(self, account_id: int) -> None:
        with self._lock:
            rid = self._room_of.pop(account_id, None)
            room = self._rooms.get(rid) if rid is not None else None
            if room:
                room.members.pop(account_id, None)

    def set_playing(self, room_id: int, account_id: int, playing: bool, capacity: int) -> None:
        with self._lock:
            room = self._rooms.get(room_id)
            if room is None or account_id not in room.members:
                raise RoomError("closed", "방을 찾을 수 없습니다")
            member = room.members[account_id]
            if playing and not member.playing and room.player_count() >= capacity:
                raise RoomError("full", "방이 가득 차서 플레이어로 참여할 수 없습니다")
            member.playing = playing

    def remove_room(self, room_id: int) -> None:
        """방이 닫혔다: 모든 사람을 내보낸다."""
        with self._lock:
            room = self._rooms.pop(room_id, None)
            if room:
                for account_id in room.members:
                    self._room_of.pop(account_id, None)

    # ---- 내부 -------------------------------------------------------------------------
    def _prune(self) -> None:
        now = self.clock()
        for room in self._rooms.values():
            for account_id, m in list(room.members.items()):
                if account_id != room.host_id and now - m.last_seen > self.member_timeout:
                    del room.members[account_id]
                    self._room_of.pop(account_id, None)


class JoinLimiter:
    """입장코드를 계속 틀리는 것을 막는다 (코드를 무작위로 맞춰 보는 시도 방지). 계정별로 센다."""

    def __init__(self, limit: int, window: float, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self._lock = threading.Lock()
        self._failures: dict[int, deque[float]] = defaultdict(deque)

    def blocked(self, account_id: int) -> bool:
        with self._lock:
            q = self._failures[account_id]
            now = self.clock()
            while q and now - q[0] > self.window:
                q.popleft()
            return len(q) >= self.limit

    def record_failure(self, account_id: int) -> None:
        with self._lock:
            self._failures[account_id].append(self.clock())

    def reset(self, account_id: int) -> None:
        with self._lock:
            self._failures.pop(account_id, None)
