"""게임 시작 API (docs/ENGINE_DESIGN.md 1-1, docs/ENGINE_SPEC.md).

방장이 시작을 누르면 확정 스냅샷을 읽어 `진행` 과 `참여` 를 만들고 방을 `진행` 상태로 바꾼다.
시작 조건: **대기실의 플레이어 수가 플레이어 캐릭터 수(NPC 가 아닌 인물 수)와 같을 때**.
플레이어가 아닌 방장은 관전자가 된다(지금은 일반 관전 하나뿐이고 GM 관전·자리 지정은 아직 없다).
"""
import asyncio
import json

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .auth import CurrentUser
from .db import Conn
from .engine import (
    AdvanceError, AssignError, Game, GameRegistry, Observer, Player, advance_phase, assign_character, hand_over_authority,
    set_paused, view_for,
)
from .rooms import find_my_room, registry

router = APIRouter(prefix="/api/rooms", tags=["game"])
state_router = APIRouter(prefix="/api/game", tags=["game"])


def games(request: Request) -> GameRegistry:
    return request.app.state.games


def _my_game(request: Request, account_id: int) -> Game:
    """내가 참여 중인 게임. 이 호출이 접속 확인(이탈 판단)을 겸한다."""
    game = games(request).of_account(account_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "진행 중인 게임이 없습니다")
    with game.lock:
        game.touch(account_id)
    return game


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


class MeOut(BaseModel):
    계정_번호: int
    역할: str
    인물_순서: int | None
    방장: bool
    진행_권한: bool


class PhaseOut(BaseModel):
    위치: int
    전체: int
    순서: int
    이름: str | None
    진행시간: int


class PlayerOut(BaseModel):
    계정_번호: int
    닉네임: str
    인물_순서: int | None
    인물_이름: str | None
    접속중: bool


class AuthorityOut(BaseModel):
    계정_번호: int
    닉네임: str
    임시: bool


class CharacterOut(BaseModel):
    순서: int
    이름: str | None
    직업: str | None
    나이: int | None
    성별: str | None
    선택한_계정: int | None


class TimeOut(BaseModel):
    서버_시각: float
    일시정지: bool
    남은_초: int | None
    시간_종료: bool


class ProgressOut(BaseModel):
    완료: int
    전체: int


class GameStateOut(BaseModel):
    상태_버전: int
    나: MeOut
    권한: AuthorityOut
    시간: TimeOut
    선택_완료: ProgressOut
    페이즈: PhaseOut
    플레이어: list[PlayerOut]
    인물: list[CharacterOut]


@state_router.get("/me/state", response_model=GameStateOut)
def my_state(me: CurrentUser, request: Request) -> dict:
    """내가 참여 중인 게임의 현재 상태. 내가 보아도 되는 것만 돌려준다."""
    game = _my_game(request, me.계정.번호)
    return view_for(game, me.계정.번호)


class ConfirmIn(BaseModel):
    인물_순서: int


ASSIGN_STATUS = {
    "not_player": status.HTTP_403_FORBIDDEN,
    "already": status.HTTP_409_CONFLICT,
    "taken": status.HTTP_409_CONFLICT,
    "unknown": status.HTTP_422_UNPROCESSABLE_CONTENT,
}


@state_router.post("/me/confirm", response_model=GameStateOut)
def confirm_character(body: ConfirmIn, conn: Conn, me: CurrentUser, request: Request) -> dict:
    """고른 인물을 "확인"한다. 선착순으로 배정되고, 확인한 뒤에는 되돌릴 수 없다."""
    game = _my_game(request, me.계정.번호)

    def persist(account_id: int, character: int) -> None:
        conn.execute(
            'UPDATE "참여" SET "인물_순서" = %s WHERE "진행_번호" = %s AND "계정_번호" = %s',
            (character, game.id, account_id),
        )

    try:
        assign_character(game, me.계정.번호, body.인물_순서, persist)
    except AssignError as err:
        raise HTTPException(ASSIGN_STATUS.get(err.code, status.HTTP_409_CONFLICT), err.message) from err
    return view_for(game, me.계정.번호)


ADVANCE_STATUS = {
    "forbidden": status.HTTP_403_FORBIDDEN,
    "unknown": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "last": status.HTTP_409_CONFLICT,
    "condition": status.HTTP_409_CONFLICT,
}


@state_router.post("/me/advance", response_model=GameStateOut)
def advance(conn: Conn, me: CurrentUser, request: Request) -> dict:
    """다음 단계로 넘어간다(진행 권한이 있는 사람만)."""
    game = _my_game(request, me.계정.번호)

    def persist(slot: int) -> None:
        conn.execute('UPDATE "진행" SET "진행순서_순서" = %s WHERE "번호" = %s', (slot, game.id))

    try:
        advance_phase(game, me.계정.번호, persist)
    except AdvanceError as err:
        raise HTTPException(ADVANCE_STATUS.get(err.code, status.HTTP_409_CONFLICT), err.message) from err
    return view_for(game, me.계정.번호)


class PauseIn(BaseModel):
    일시정지: bool


@state_router.post("/me/pause", response_model=GameStateOut)
def pause(body: PauseIn, me: CurrentUser, request: Request) -> dict:
    """시간을 멈추거나 다시 흐르게 한다(진행 권한이 있는 사람만)."""
    game = _my_game(request, me.계정.번호)
    try:
        set_paused(game, me.계정.번호, body.일시정지)
    except AdvanceError as err:
        raise HTTPException(ADVANCE_STATUS.get(err.code, status.HTTP_409_CONFLICT), err.message) from err
    return view_for(game, me.계정.번호)


class AuthorityIn(BaseModel):
    계정_번호: int


@state_router.post("/me/authority", response_model=GameStateOut)
def give_authority(body: AuthorityIn, me: CurrentUser, request: Request) -> dict:
    """방장이 진행 권한을 특정 플레이어에게 맡긴다(자기 자신에게 맡기면 되돌린다)."""
    game = _my_game(request, me.계정.번호)
    try:
        hand_over_authority(game, me.계정.번호, body.계정_번호)
    except AdvanceError as err:
        raise HTTPException(ADVANCE_STATUS.get(err.code, status.HTTP_409_CONFLICT), err.message) from err
    return view_for(game, me.계정.번호)


# ---- 실시간 알림(SSE) ----------------------------------------------------------------------

KEEPALIVE_SECONDS = 15.0     # 이 시간마다 연결이 살아 있다는 신호를 보내고, 그때 접속 확인(이탈 판단)도 갱신한다


def sse_message(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@state_router.get("/me/events")
async def events(request: Request, me: CurrentUser) -> StreamingResponse:
    """상태가 바뀌었음을 알리는 SSE 연결. 알림에는 상태 버전만 싣고, 화면은 그때 상태를 다시 조회한다.

    인증은 일반 요청과 같은 `Authorization: Bearer` 헤더이다(화면은 `fetch` 로 이 스트림을 읽는다).
    연결과 게임의 진행은 분리되어 있어서 연결이 끊겨도 게임은 계속 진행된다. 연결이 살아 있는 동안은 접속 중으로 본다.
    """
    account_id = me.계정.번호
    game = _my_game(request, account_id)
    queue = game.subscribe(asyncio.get_running_loop())

    async def stream():
        try:
            yield sse_message("version", {"상태_버전": game.state_version})
            while not await request.is_disconnected():
                try:
                    version = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                    while not queue.empty():            # 밀린 알림은 가장 새 버전 하나로 합친다
                        version = queue.get_nowait()
                    game.touch(account_id)
                    yield sse_message("version", {"상태_버전": version})
                except asyncio.TimeoutError:
                    game.touch(account_id)
                    if games(request).get(game.room_id) is not game:
                        yield sse_message("closed", {})
                        return
                    yield ": ping\n\n"
        finally:
            game.unsubscribe(queue)

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
