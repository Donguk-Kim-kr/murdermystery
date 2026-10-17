"""게임 시작 API (docs/ENGINE_DESIGN.md 1-1, docs/ENGINE_SPEC.md).

방장이 시작을 누르면 확정 스냅샷을 읽어 `진행` 과 `참여` 를 만들고 방을 `진행` 상태로 바꾼다.
시작 조건: **대기실의 플레이어 수가 플레이어 캐릭터 수(NPC 가 아닌 인물 수)와 같을 때**.
플레이어가 아닌 방장은 관전자가 된다(지금은 일반 관전 하나뿐이고 GM 관전·자리 지정은 아직 없다).
"""
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from .auth import CurrentUser
from .db import Conn
from .engine import Game, GameRegistry, Observer, Player
from .rooms import find_my_room, registry

router = APIRouter(prefix="/api/rooms", tags=["game"])


def games(request: Request) -> GameRegistry:
    return request.app.state.games


class MemberRef(BaseModel):
    계정_번호: int
    닉네임: str


class StartOut(BaseModel):
    진행_번호: int
    방_번호: int
    현재_페이즈_순서: int
    플레이어: list[MemberRef]
    관전자: list[MemberRef]


@router.post("/me/start", response_model=StartOut)
def start_game(conn: Conn, me: CurrentUser, request: Request) -> StartOut:
    """내 방의 게임을 시작한다. 방장만 할 수 있다."""
    mine = find_my_room(conn, registry(request), me)
    if mine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "참여 중인 방이 없습니다")
    row, room = mine
    if room.host_id != me.계정.번호:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "방장만 시작할 수 있습니다")

    # 같은 방을 동시에 두 번 시작하지 못하게 방 행을 잠그고 상태를 다시 확인한다.
    locked = conn.execute('SELECT "상태" FROM "방" WHERE "번호" = %s FOR UPDATE', (row["번호"],)).fetchone()
    if locked is None or locked["상태"] != "대기":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 시작했거나 종료된 방입니다")

    version = conn.execute(
        'SELECT "시나리오" FROM "버전" WHERE "작품_번호" = %s AND "버전" = %s', (row["작품_번호"], row["버전_버전"])
    ).fetchone()
    snapshot = version["시나리오"] if version else None
    phases = sorted((snapshot or {}).get("진행순서") or [], key=lambda p: p["순서"])
    characters = (snapshot or {}).get("인물") or []
    if not phases or not characters:
        raise HTTPException(status.HTTP_409_CONFLICT, "확정된 작품에 진행 순서나 인물이 없어 시작할 수 없습니다")

    need = sum(1 for c in characters if not c.get("NPC"))
    joined = [m for m in room.members.values() if m.playing]
    if len(joined) != need:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"플레이어 수({len(joined)}명)가 캐릭터 수({need}명)와 같아야 시작할 수 있습니다",
        )

    created = conn.execute(
        'INSERT INTO "진행" ("방_번호", "작품_번호", "버전_버전", "진행순서_순서") VALUES (%s, %s, %s, %s) RETURNING "번호"',
        (row["번호"], row["작품_번호"], row["버전_버전"], phases[0]["순서"]),
    ).fetchone()
    for m in joined:
        conn.execute(
            'INSERT INTO "참여" ("작품_번호", "진행_번호", "계정_번호") VALUES (%s, %s, %s)',
            (row["작품_번호"], created["번호"], m.account_id),
        )
    conn.execute('UPDATE "방" SET "상태" = \'진행\' WHERE "번호" = %s', (row["번호"],))

    game = Game(
        id=created["번호"], room_id=row["번호"], work_id=row["작품_번호"], version=row["버전_버전"], host_id=room.host_id,
        snapshot=snapshot,
        players={m.account_id: Player(m.account_id, m.nickname) for m in joined},
        observers={m.account_id: Observer(m.account_id, m.nickname) for m in room.members.values() if not m.playing},
    )
    games(request).add(game)
    return StartOut(
        진행_번호=game.id, 방_번호=game.room_id, 현재_페이즈_순서=phases[0]["순서"],
        플레이어=[MemberRef(계정_번호=p.account_id, 닉네임=p.nickname) for p in game.players.values()],
        관전자=[MemberRef(계정_번호=o.account_id, 닉네임=o.nickname) for o in game.observers.values()],
    )
