"""게임 시작 API (docs/ENGINE_DESIGN.md 1-1, docs/ENGINE_SPEC.md).

방장이 시작을 누르면 확정 스냅샷을 읽어 `진행` 과 `참여` 를 만들고 방을 `진행` 상태로 바꾼다.
시작 조건: **대기실의 플레이어 수가 최소인원 이상, 최대인원(NPC 가 아닌 인물 수) 이하일 때**. 최대보다 적게 시작하면 모자란 만큼의 인물이 NPC 가 된다.
어느 인물이 NPC 가 되는지는 제작자가 정한 순위(`인물.NPC순위`, 1 이 먼저)대로 이 게임을 시작할 때 정해진다(사용자 2026-10-18).
플레이어가 아닌 방장은 관전자가 된다(지금은 일반 관전 하나뿐이고 GM 관전·자리 지정은 아직 없다).
"""
import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .auth import CurrentUser
from .db import Conn
from . import cards
from .cards import AnswerError
from .engine import (
    AdvanceError, Game, GameIO, GameRegistry, Observer, Player, advance_phase, hand_over_authority, set_auto_advance,
    set_paused, view_for,
)
from .rooms import find_my_room, registry

router = APIRouter(prefix="/api/rooms", tags=["game"])
state_router = APIRouter(prefix="/api/game", tags=["game"])


def games(request: Request) -> GameRegistry:
    return request.app.state.games


ACQUIRE_COLUMNS = {"단서": "단서_순서", "증언": "증언_순서"}


def acquire_sql(kind: str) -> str:
    """획득 기록을 남기는 문장. 컬럼 이름은 고정 목록에서만 고른다."""
    column = ACQUIRE_COLUMNS[kind]
    return (
        f'INSERT INTO "획득" ("작품_번호", "진행_번호", "참여_번호", "{column}", "진행순서_순서", "획득방법") '
        'SELECT "작품_번호", "진행_번호", "번호", %s, %s, %s FROM "참여" WHERE "진행_번호" = %s AND "계정_번호" = %s'
    )


def vote_sql() -> str:
    """표를 남기는 문장(이미 했으면 고른 것을 바꾼다). 파라미터는 (투표 이름, 고른 것, 진행 번호, 계정 번호)."""
    return (
        'INSERT INTO "투표결과" ("작품_번호", "투표이름", "참여_번호", "선택") '
        'SELECT "작품_번호", %s, "번호", %s FROM "참여" WHERE "진행_번호" = %s AND "계정_번호" = %s '
        'ON CONFLICT ("작품_번호", "투표이름", "참여_번호") DO UPDATE SET "선택" = EXCLUDED."선택"'
    )


def _own_row(column: str = "g") -> str:
    """(진행, 계정, 단서 순서) 로 지금 보유 중인 획득 행을 고르는 조건. 앞의 세 값이 순서대로 파라미터이다."""
    return (
        f'{column}."진행_번호" = %s AND {column}."보유여부" AND {column}."단서_순서" = %s AND '
        f'{column}."참여_번호" = (SELECT "번호" FROM "참여" WHERE "진행_번호" = %s AND "계정_번호" = %s)'
    )


def transfer_statements(game_id: int, giver: int, taker: int, order: int, slot: int) -> list[tuple[str, tuple]]:
    """양도: 그 단서에 걸린 공개를 취소하고, 준 사람의 획득을 끄고, 받은 사람의 획득을 새로 남긴다."""
    own = _own_row("g")
    own_args = (game_id, order, game_id, giver)
    return [
        (
            'UPDATE "공개" SET "취소일시" = CURRENT_TIMESTAMP WHERE "취소일시" IS NULL AND "획득_번호" IN '
            f'(SELECT g."번호" FROM "획득" g WHERE {own})',
            own_args,
        ),
        (f'UPDATE "획득" g SET "보유여부" = FALSE WHERE {own}', own_args),
        (
            'INSERT INTO "획득" ("작품_번호", "진행_번호", "참여_번호", "단서_순서", "진행순서_순서", "획득방법") '
            'SELECT "작품_번호", "진행_번호", "번호", %s, %s, \'양도\' FROM "참여" WHERE "진행_번호" = %s AND "계정_번호" = %s',
            (order, slot, game_id, taker),
        ),
    ]


def reveal_statement(game_id: int, owner: int, order: int, target: int | None) -> tuple[str, tuple]:
    own = _own_row("g")
    return (
        'INSERT INTO "공개" ("작품_번호", "진행_번호", "획득_번호", "대상_참여_번호") '
        f'SELECT g."작품_번호", g."진행_번호", g."번호", (SELECT "번호" FROM "참여" WHERE "진행_번호" = %s AND "계정_번호" = %s) '
        f'FROM "획득" g WHERE {own}',
        (game_id, target, game_id, order, game_id, owner),
    )


def unreveal_statement(game_id: int, owner: int, order: int, target: int | None) -> tuple[str, tuple]:
    own = _own_row("g")
    return (
        'UPDATE "공개" SET "취소일시" = CURRENT_TIMESTAMP WHERE "취소일시" IS NULL AND '
        f'"대상_참여_번호" IS NOT DISTINCT FROM (SELECT "번호" FROM "참여" WHERE "진행_번호" = %s AND "계정_번호" = %s) AND '
        f'"획득_번호" IN (SELECT g."번호" FROM "획득" g WHERE {own})',
        (game_id, target, game_id, order, game_id, owner),
    )


def build_io(game: Game, run) -> GameIO:
    """`run(문장, 값)` 으로 DB 에 쓰는 GameIO. 요청 안에서는 요청의 연결로, 요청 밖에서는 연결을 빌려서 쓴다."""
    return GameIO(
        phase=lambda slot: run('UPDATE "진행" SET "진행순서_순서" = %s WHERE "번호" = %s', (slot, game.id)),
        assign=lambda account, slot: run(
            'UPDATE "참여" SET "인물_순서" = %s WHERE "진행_번호" = %s AND "계정_번호" = %s', (slot, game.id, account)
        ),
        end=lambda: run('UPDATE "진행" SET "상태" = \'종료\' WHERE "번호" = %s', (game.id,)),
        acquire=lambda account, kind, order, slot, method: run(acquire_sql(kind), (order, slot, method, game.id, account)),
        transfer=lambda giver, taker, order, slot: [run(*st) for st in transfer_statements(game.id, giver, taker, order, slot)],
        reveal=lambda owner, order, target: run(*reveal_statement(game.id, owner, order, target)),
        unreveal=lambda owner, order, target: run(*unreveal_statement(game.id, owner, order, target)),
        vote=lambda account, name, choice: run(vote_sql(), (name, choice, game.id, account)),
        clear_votes=lambda name: run(
            'DELETE FROM "투표결과" WHERE "투표이름" = %s AND "참여_번호" IN (SELECT "번호" FROM "참여" WHERE "진행_번호" = %s)', (name, game.id)
        ),
    )


def conn_io(conn, game: Game) -> GameIO:
    """요청의 DB 연결로 게임이 남길 기록을 쓴다(요청이 끝날 때 함께 확정된다)."""
    return build_io(game, lambda sql_text, params: conn.execute(sql_text, params))


def pool_io(pool, game: Game) -> GameIO:
    """요청 밖(주기 작업)에서 쓴다: 기록할 때마다 연결을 빌려 바로 확정한다."""

    def run(sql_text: str, params: tuple) -> None:
        with pool.connection() as conn:
            conn.execute(sql_text, params)

    return build_io(game, run)


def _my_game(request: Request, account_id: int) -> Game:
    """내가 참여 중인 게임. 이 호출이 접속 확인(이탈 판단)을 겸한다."""
    game = games(request).of_account(account_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "진행 중인 게임이 없습니다")
    with game.lock:
        game.touch(account_id)
    return game


class GameMemberRef(BaseModel):
    계정_번호: int
    닉네임: str


class StartOut(BaseModel):
    진행_번호: int
    방_번호: int
    현재_페이즈_순서: int
    플레이어: list[GameMemberRef]
    관전자: list[GameMemberRef]


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

    joined = [m for m in room.members.values() if m.playing]
    try:
        npc_slots = npc_slots_for(characters, len(joined))
    except ValueError as err:
        raise HTTPException(status.HTTP_409_CONFLICT, str(err)) from None

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
        snapshot=snapshot, npc_slots=npc_slots,
        players={m.account_id: Player(m.account_id, m.nickname) for m in joined},
        observers={m.account_id: Observer(m.account_id, m.nickname, m.gm) for m in room.members.values() if not m.playing},
    )
    games(request).add(game)
    with game.lock:
        cards.start_phase(game, conn_io(conn, game))      # 첫 페이즈의 카드가 실행을 시작한다
    return StartOut(
        진행_번호=game.id, 방_번호=game.room_id, 현재_페이즈_순서=phases[0]["순서"],
        플레이어=[GameMemberRef(계정_번호=p.account_id, 닉네임=p.nickname) for p in game.players.values()],
        관전자=[GameMemberRef(계정_번호=o.account_id, 닉네임=o.nickname) for o in game.observers.values()],
    )


def npc_slots_for(characters: list[dict[str, Any]], players: int) -> set[int]:
    """플레이어 수에 맞게 이 게임에서 NPC 가 되는 인물(순서)을 정한다. 인원이 허용 범위 밖이면 ValueError(메시지는 그대로 보여 준다).

    최대 = NPC 가 아닌 인물 수, 최소 = 최대 - NPC 가 될 수 있는 인물 수. 모자란 인원만큼 NPC 순위가 낮은 숫자(먼저)인 인물이 NPC 가 된다.
    """
    playable = [c for c in characters if not c.get("NPC")]
    ranked = sorted((c["NPC순위"], c["순서"]) for c in playable if c.get("NPC순위") is not None)
    most = len(playable)
    least = max(most - len(ranked), 1)
    if not least <= players <= most:
        span = f"{most}명" if least == most else f"{least}명 이상 {most}명 이하"
        raise ValueError(f"플레이어 수({players}명)가 허용 인원({span})이어야 시작할 수 있습니다")
    return {slot for _, slot in ranked[: most - players]}


class GameMeOut(BaseModel):
    계정_번호: int
    역할: str
    인물_순서: int | None
    방장: bool
    진행_권한: bool
    관전방식: str | None = None   # 관전자일 때 "GM" 또는 "일반"


class GamePhaseOut(BaseModel):
    위치: int
    전체: int
    순서: int
    이름: str | None
    진행시간: int


class GamePlayerOut(BaseModel):
    계정_번호: int
    닉네임: str
    인물_순서: int | None
    인물_이름: str | None
    접속중: bool


class GameAuthorityOut(BaseModel):
    계정_번호: int
    닉네임: str
    임시: bool


class GameCharacterOut(BaseModel):
    순서: int
    이름: str | None
    직업: str | None
    나이: int | None
    성별: str | None
    선택한_계정: int | None


class GameTimeOut(BaseModel):
    서버_시각: float
    일시정지: bool
    남은_초: int | None
    시간_종료: bool


class GameProgressOut(BaseModel):
    완료: int
    전체: int


class GameSettingsOut(BaseModel):
    자동_진행: bool


class GameStateOut(BaseModel):
    상태_버전: int
    화면: list[dict[str, Any]]
    탭: list[dict[str, Any]]
    알림: list[dict[str, Any]]
    오류: list[dict[str, Any]]
    종료: bool
    설정: GameSettingsOut
    나: GameMeOut
    권한: GameAuthorityOut
    시간: GameTimeOut
    선택_완료: GameProgressOut
    페이즈: GamePhaseOut
    플레이어: list[GamePlayerOut]
    인물: list[GameCharacterOut]


@state_router.get("/me/state", response_model=GameStateOut)
def my_state(me: CurrentUser, request: Request) -> dict:
    """내가 참여 중인 게임의 현재 상태. 내가 보아도 되는 것만 돌려준다."""
    game = _my_game(request, me.계정.번호)
    return view_for(game, me.계정.번호)


class GameAnswerIn(BaseModel):
    질문ID: str
    값: Any = None


ANSWER_STATUS = {
    "not_player": status.HTTP_403_FORBIDDEN,
    "stale": status.HTTP_409_CONFLICT,
    "ended": status.HTTP_409_CONFLICT,
    "invalid": status.HTTP_422_UNPROCESSABLE_CONTENT,
}


@state_router.post("/me/answer", response_model=GameStateOut)
def answer(body: GameAnswerIn, conn: Conn, me: CurrentUser, request: Request) -> dict:
    """화면의 질문(블록의 `질문ID`)에 답한다. 지금 받지 않는 질문이면 거부한다. 입력은 한 번에 하나씩 처리된다."""
    game = _my_game(request, me.계정.번호)
    with game.lock:
        try:
            cards.answer(game, me.계정.번호, body.질문ID, body.값, conn_io(conn, game))
        except AnswerError as err:
            raise HTTPException(ANSWER_STATUS.get(err.code, status.HTTP_409_CONFLICT), err.message) from err
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

    try:
        advance_phase(game, me.계정.번호, conn_io(conn, game))
    except AdvanceError as err:
        raise HTTPException(ADVANCE_STATUS.get(err.code, status.HTTP_409_CONFLICT), err.message) from err
    return view_for(game, me.계정.번호)


class GamePauseIn(BaseModel):
    일시정지: bool


@state_router.post("/me/pause", response_model=GameStateOut)
def pause(body: GamePauseIn, me: CurrentUser, request: Request) -> dict:
    """시간을 멈추거나 다시 흐르게 한다(진행 권한이 있는 사람만)."""
    game = _my_game(request, me.계정.번호)
    try:
        set_paused(game, me.계정.번호, body.일시정지)
    except AdvanceError as err:
        raise HTTPException(ADVANCE_STATUS.get(err.code, status.HTTP_409_CONFLICT), err.message) from err
    return view_for(game, me.계정.번호)


class GameAuthorityIn(BaseModel):
    계정_번호: int


@state_router.post("/me/authority", response_model=GameStateOut)
def give_authority(body: GameAuthorityIn, me: CurrentUser, request: Request) -> dict:
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


class GameSettingsIn(BaseModel):
    자동_진행: bool


@state_router.post("/me/settings", response_model=GameStateOut)
def change_settings(body: GameSettingsIn, me: CurrentUser, request: Request) -> dict:
    """시간이 끝나면 저절로 다음 단계로 넘어갈지 고른다(방장만). 기본은 방장이 넘기기 전에는 넘어가지 않는 것이다."""
    game = _my_game(request, me.계정.번호)
    try:
        set_auto_advance(game, me.계정.번호, body.자동_진행)
    except AdvanceError as err:
        raise HTTPException(ADVANCE_STATUS.get(err.code, status.HTTP_409_CONFLICT), err.message) from err
    return view_for(game, me.계정.번호)
