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
    authority_id: int = 0            # 진행 권한(다음 단계로 넘기기 등)을 가진 계정. 처음에는 방장이다
    phase_index: int = 0             # 흐름 안의 위치(0부터)
    state_version: int = 1           # 상태가 바뀔 때마다 올라간다(화면이 오래된 응답을 거르는 데 쓴다)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    @property
    def phases(self) -> list[dict[str, Any]]:
        return sorted(self.snapshot.get("진행순서") or [], key=lambda p: p["순서"])

    @property
    def phase(self) -> dict[str, Any]:
        return self.phases[self.phase_index]

    def __post_init__(self) -> None:
        if not self.authority_id:
            self.authority_id = self.host_id

    @property
    def characters(self) -> list[dict[str, Any]]:
        """플레이어가 맡는 인물(NPC 가 아닌 것)."""
        return [c for c in (self.snapshot.get("인물") or []) if not c.get("NPC")]

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
            "페이즈": {
                "위치": game.phase_index + 1,
                "전체": len(game.phases),
                "순서": phase["순서"],
                "이름": phase.get("표시이름"),
                "진행시간": phase["진행시간"],
            },
            "선택_완료": {"완료": sum(1 for p in game.players.values() if p.character is not None), "전체": len(game.players)},
            "플레이어": [
                {
                    "계정_번호": p.account_id,
                    "닉네임": p.nickname,
                    "인물_순서": p.character,
                    "인물_이름": by_slot[p.character]["이름"] if p.character in by_slot else None,
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
