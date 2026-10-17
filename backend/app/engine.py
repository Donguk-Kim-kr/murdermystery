"""게임 진행 엔진의 상태 (docs/ENGINE_SPEC.md, docs/ENGINE_DESIGN.md 1-8·1-9).

게임이 시작되면 방마다 `Game` 이 하나 생긴다. 진행 중인 상태(현재 페이즈, 누가 어떤 인물인지, 상태 버전 등)는
서버 메모리에 두고, 기록으로 남아야 하는 것(진행, 참여, 인물 배정)은 DB 에 쓴다. 서버를 다시 시작하면 진행 중이던 게임은
이어지지 않는다(기존 결정: 서버 재시작은 지금 고려하지 않는다). 서버는 프로세스 하나로만 실행한다.

확정 스냅샷(`버전.시나리오`)을 게임이 시작될 때 한 번 읽어 와서 `snapshot` 에 들고 있는다. 이후 제작용 콘텐츠가 바뀌어도
진행 중인 게임은 영향을 받지 않는다.
"""
import asyncio
import threading
import time
from collections.abc import Callable
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
    designated_id: int = 0           # 방장이 진행 권한을 맡긴 계정. 처음에는 방장이다
    away_seconds: float = 600.0
    last_seen: dict[int, float] = field(default_factory=dict)   # 계정 → 마지막으로 상태를 확인한 시각
    phase_index: int = 0             # 흐름 안의 위치(0부터)
    auto_advance: bool = False       # 시간이 끝나면 저절로 다음 단계로 넘어갈지(방장이 고른다). 기본은 방장이 넘기기 전에는 넘어가지 않는다
    ended: bool = False              # 게임 종료(전체 공개 단계가 시작된 뒤). 방은 이로부터 6시간 뒤에 종료된다
    state_version: int = 1           # 상태가 바뀔 때마다 올라간다(화면이 오래된 응답을 거르는 데 쓴다)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    clock: Callable[[], float] = time.time
    # 시간: 지금 페이즈에서 흐른 시간 = elapsed_base + (달리는 중이면 지금 - running_since)
    elapsed_base: float = 0.0
    running_since: float | None = None
    # 다음 단계로 넘어가려 할 때 묻는 조건들. 안내 메시지를 돌려주면 넘어가지 못한다(없으면 통과). 카드의 `진행조건` 이 채운다.
    advance_conditions: list[Callable[["Game"], str | None]] = field(default_factory=list, repr=False)
    # 상태가 바뀌었다는 알림을 받는 연결들(SSE). 알림은 "바뀌었으니 다시 조회하라"는 신호이고 상태 자체를 싣지 않는다.
    _listeners: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = field(default_factory=list, repr=False)

    @property
    def phases(self) -> list[dict[str, Any]]:
        return sorted(self.snapshot.get("진행순서") or [], key=lambda p: p["순서"])

    @property
    def phase(self) -> dict[str, Any]:
        return self.phases[self.phase_index]

    def __post_init__(self) -> None:
        if not self.designated_id:
            self.designated_id = self.host_id
        self.running_since = self.clock()
        now = self.clock()
        self.last_seen = {a: now for a in [*self.players, *self.observers]}

    @property
    def characters(self) -> list[dict[str, Any]]:
        """플레이어가 맡는 인물(NPC 가 아닌 것)."""
        return [c for c in (self.snapshot.get("인물") or []) if not c.get("NPC")]

    def bump(self) -> int:
        self.state_version += 1
        version = self.state_version
        for loop, queue in list(self._listeners):
            try:
                loop.call_soon_threadsafe(queue.put_nowait, version)
            except RuntimeError:        # 연결의 이벤트 루프가 이미 닫혔다
                self.unsubscribe(queue)
        return version

    def subscribe(self, loop: asyncio.AbstractEventLoop) -> asyncio.Queue:
        """상태가 바뀔 때마다 새 상태 버전을 받는 대기열을 만든다. 쓰고 나면 `unsubscribe` 로 해제한다."""
        queue: asyncio.Queue = asyncio.Queue()
        with self.lock:
            self._listeners.append((loop, queue))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self.lock:
            self._listeners[:] = [(l, q) for l, q in self._listeners if q is not queue]

    # ---- 접속과 진행 권한 ----------------------------------------------------------------
    def touch(self, account_id: int) -> None:
        self.last_seen[account_id] = self.clock()

    def away(self, account_id: int) -> bool:
        """상태 확인이 유예 시간 동안 끊겼으면 이탈로 본다(자리와 인물은 그대로 유지된다)."""
        return self.clock() - self.last_seen.get(account_id, 0.0) > self.away_seconds

    def eligible(self) -> list[int]:
        """진행 권한을 가질 수 있는 사람의 우선순서. 맡겨진 사람 → 방장 → 입장한 순서의 플레이어.

        관전자는 갖지 못한다(관전 모드는 일반 관전뿐이다). 방장이 플레이하지 않으면 방장은 빠지고 첫 플레이어가 된다.
        """
        order: list[int] = []
        for account in [self.designated_id, self.host_id, *self.players]:
            if account in self.players and account not in order:
                order.append(account)
        return order

    @property
    def authority_id(self) -> int:
        """지금 진행 권한을 가진 계정. 우선순서에서 이탈하지 않은 첫 사람이다. 모두 이탈했으면 맡겨진 사람(없으면 첫 사람)."""
        order = self.eligible()
        for account in order:
            if not self.away(account):
                return account
        return order[0] if order else self.host_id

    # ---- 시간 ------------------------------------------------------------------------
    @property
    def paused(self) -> bool:
        return self.running_since is None

    @property
    def duration(self) -> float | None:
        """지금 페이즈의 제한 시간(초). 0분은 시간 제한이 없는 것으로 본다."""
        minutes = self.phase["진행시간"]
        return minutes * 60.0 if minutes else None

    def elapsed(self) -> float:
        return self.elapsed_base + (0.0 if self.running_since is None else self.clock() - self.running_since)

    def remaining(self) -> float | None:
        if self.duration is None:
            return None
        return max(0.0, self.duration - self.elapsed())

    def restart_timer(self) -> None:
        self.elapsed_base = 0.0
        self.running_since = self.clock()


class GameRegistry:
    """진행 중인 게임을 방 번호로 찾는다."""

    def __init__(self, clock: Callable[[], float] = time.time, away_seconds: float = 600.0) -> None:
        self.clock = clock               # 테스트에서 시간을 흘려 보내기 위해 바꿀 수 있다
        self.away_seconds = away_seconds
        self._lock = threading.RLock()
        self._games: dict[int, Game] = {}

    def add(self, game: Game) -> None:
        with self._lock:
            game.clock = lambda: self.clock()   # 등록한 레지스트리의 시계를 따른다
            game.away_seconds = self.away_seconds
            game.restart_timer()
            game.last_seen = {a: game.clock() for a in [*game.players, *game.observers]}
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

    def all(self) -> list[Game]:
        with self._lock:
            return list(self._games.values())

    def remove(self, room_id: int) -> None:
        with self._lock:
            self._games.pop(room_id, None)


# 모든 보는 사람에게 보여도 되는 인물 정보. 서사·비밀·능력·목표·범인 같은 것은 여기에 없다.
PUBLIC_CHARACTER_FIELDS = ("이름", "직업", "나이", "성별")


def view_for(game: Game, account_id: int) -> dict[str, Any]:
    """`account_id` 가 보아도 되는 게임 상태. 비공개 내용은 이 함수가 만드는 값에 들어가지 않는다."""
    with game.lock:
        player = game.players.get(account_id)
        if player is None and account_id not in game.observers:
            raise KeyError(account_id)
        phase = game.phase
        taken = {p.character: p for p in game.players.values() if p.character is not None}
        by_slot = {c["순서"]: c for c in game.characters}
        return {
            "상태_버전": game.state_version,
            "나": {
                "계정_번호": account_id,
                "역할": "플레이어" if player else "관전자",
                "인물_순서": player.character if player else None,
                "방장": account_id == game.host_id,
                "진행_권한": account_id == game.authority_id,
            },
            "권한": _authority_view(game),
            "종료": game.ended,
            "설정": {"자동_진행": game.auto_advance},
            "페이즈": {
                "위치": game.phase_index + 1,
                "전체": len(game.phases),
                "순서": phase["순서"],
                "이름": phase.get("표시이름"),
                "진행시간": phase["진행시간"],
            },
            "시간": _time_view(game),
            "선택_완료": {"완료": sum(1 for p in game.players.values() if p.character is not None), "전체": len(game.players)},
            "플레이어": [
                {
                    "계정_번호": p.account_id,
                    "닉네임": p.nickname,
                    "인물_순서": p.character,
                    "인물_이름": by_slot[p.character]["이름"] if p.character in by_slot else None,
                    "접속중": not game.away(p.account_id),
                }
                for p in game.players.values()
            ],
            "인물": [
                {
                    "순서": c["순서"],
                    **{f: c.get(f) for f in PUBLIC_CHARACTER_FIELDS},
                    "선택한_계정": taken[c["순서"]].account_id if c["순서"] in taken else None,
                }
                for c in game.characters
            ],
        }


class AssignError(Exception):
    """배정할 수 없다. `code` 로 API 계층이 응답을 정한다."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def assign_character(game: Game, account_id: int, character: int, persist) -> None:
    """플레이어에게 인물을 배정한다(선착순, 한 번에 하나씩). 확인한 뒤에는 되돌릴 수 없다.

    `persist(account_id, character)` 는 DB 에 쓰는 함수이고, 메모리를 바꾸기 전에 호출한다.
    같은 인물을 둘이 고르면 먼저 들어온 요청만 성공한다.
    """
    with game.lock:
        if game.ended:
            raise AssignError("ended", "게임이 끝났습니다")
        player = game.players.get(account_id)
        if player is None:
            raise AssignError("not_player", "플레이어만 캐릭터를 고를 수 있습니다")
        if player.character is not None:
            raise AssignError("already", "이미 캐릭터를 선택했습니다")
        if character not in {c["순서"] for c in game.characters}:
            raise AssignError("unknown", "고를 수 없는 인물입니다")
        if any(p.character == character for p in game.players.values()):
            raise AssignError("taken", "이미 다른 사람이 고른 인물입니다")
        persist(account_id, character)
        player.character = character
        game.bump()


def confirmed_count(game: Game) -> int:
    """캐릭터를 확인한 플레이어 수."""
    with game.lock:
        return sum(1 for p in game.players.values() if p.character is not None)


class AdvanceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _time_view(game: Game) -> dict[str, Any]:
    now = game.clock()
    remaining = game.remaining()
    return {
        "서버_시각": now,
        "일시정지": game.paused,
        "남은_초": None if remaining is None else int(remaining + 0.999),
        "시간_종료": remaining is not None and remaining <= 0,
    }


def set_paused(game: Game, account_id: int, paused: bool) -> None:
    """시간을 멈추거나 다시 흐르게 한다. 진행 권한이 있는 사람만 할 수 있다."""
    with game.lock:
        if account_id != game.authority_id:
            raise AdvanceError("forbidden", "진행 권한이 있는 사람만 할 수 있습니다")
        if paused == game.paused:
            return
        if paused:
            game.elapsed_base = game.elapsed()
            game.running_since = None
        else:
            game.running_since = game.clock()
        game.bump()


def _advance(game: Game, persist: Callable[[int], None]) -> None:
    """권한과 상관없이 다음 단계로 넘어가는 핵심 동작. 호출하는 쪽이 `game.lock` 을 잡고 있어야 한다."""
    if game.ended:
        raise AdvanceError("last", "게임이 끝났습니다")
    if game.phase_index >= len(game.phases) - 1:
        raise AdvanceError("last", "마지막 단계입니다")
    for condition in game.advance_conditions:
        message = condition(game)
        if message:
            raise AdvanceError("condition", message)
    persist(game.phases[game.phase_index + 1]["순서"])
    game.phase_index += 1
    game.restart_timer()
    game.bump()


def advance_phase(game: Game, account_id: int, persist: Callable[[int], None]) -> None:
    """다음 단계로 넘어간다. 진행 권한이 있는 사람만 할 수 있고, 카드의 진행 조건이 맞아야 한다.

    시간이 남아 있어도(조기 진행), 일시정지 중이어도 넘길 수 있다. `persist(순서)` 는 새 페이즈를 DB 에 쓴다.
    """
    with game.lock:
        if account_id != game.authority_id:
            raise AdvanceError("forbidden", "진행 권한이 있는 사람만 넘길 수 있습니다")
        _advance(game, persist)


def set_auto_advance(game: Game, account_id: int, value: bool) -> None:
    """시간이 끝나면 저절로 넘어갈지 고른다. 방장만 할 수 있다."""
    with game.lock:
        if account_id != game.host_id:
            raise AdvanceError("forbidden", "방장만 바꿀 수 있습니다")
        if value != game.auto_advance:
            game.auto_advance = value
            game.bump()


def auto_advance_if_due(game: Game, persist: Callable[[int], None]) -> bool:
    """자동 진행이 켜져 있고 시간이 끝났으면 다음 단계로 넘어간다. 진행 조건이 맞지 않거나 마지막 단계면 그대로 기다린다.

    일시정지 중이거나 시간 제한이 없는 단계는 넘어가지 않는다. 넘어갔으면 True.
    """
    with game.lock:
        if not game.auto_advance or game.ended or game.paused:
            return False
        remaining = game.remaining()
        if remaining is None or remaining > 0:
            return False
        try:
            _advance(game, persist)
        except AdvanceError:
            return False
        return True


def end_game(game: Game, persist: Callable[[], None]) -> None:
    """게임을 끝낸다(전체 공개 단계가 시작될 때 스크립트가 부른다). 방은 이로부터 6시간 뒤에 종료된다(방 정리가 처리)."""
    with game.lock:
        if game.ended:
            return
        persist()
        game.ended = True
        game.bump()


def _authority_view(game: Game) -> dict[str, Any]:
    holder = game.authority_id
    names = {**{a: p.nickname for a, p in game.players.items()}, **{a: o.nickname for a, o in game.observers.items()}}
    return {"계정_번호": holder, "닉네임": names.get(holder, ""), "임시": holder != game.designated_id}


def hand_over_authority(game: Game, account_id: int, target: int) -> None:
    """방장이 진행 권한을 특정 플레이어에게 맡긴다(자기 자신에게 맡기면 되돌린다). 방장만 할 수 있다."""
    with game.lock:
        if account_id != game.host_id:
            raise AdvanceError("forbidden", "방장만 진행 권한을 맡길 수 있습니다")
        if target not in game.players:
            raise AdvanceError("unknown", "플레이어에게만 맡길 수 있습니다")
        game.designated_id = target
        game.bump()
