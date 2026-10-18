"""게임 채팅 (사용자 결정 2026-10-18, docs/BACKLOG.md "게임 채팅").

* 채팅 장소는 **전체**와 **밀담 A, 밀담 B …** 이다. 밀담 장소의 수는 플레이어 수 ÷ 2(내림)이고, 밀담 장소에는 2명까지 들어갈 수 있다.
* 플레이어는 한 번에 한 장소에만 있고(처음에는 전체), 누구의 위치든 모두에게 보인다. 장소는 자유롭게 옮긴다(신청·수락 없음).
* 메시지는 **보낼 때 그 장소에 있던 플레이어**에게만 보인다(대화수신에 남긴다). 나중에 들어온 사람, 다른 장소에 가 있던 사람은
  그 메시지를 보지 못한다. 게임이 끝난 뒤에도 같다.
* 관전자는 쓰지 못한다. 일반 관전은 전체 장소의 메시지를 모두 읽고, GM 관전은 밀담 포함 모든 메시지를 읽는다. 위치는 모두 본다.
* 기록은 DB 에 남긴다(대화·대화수신). 위치는 메모리에만 있다.
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from .auth import CurrentUser
from .db import Conn
from .engine import Game

router = APIRouter(prefix="/api/game/me/chat", tags=["chat"])

ALL_PLACE = "전체"
SECRET_CAPACITY = 2        # 밀담 장소 하나에 들어갈 수 있는 인원
MAX_TEXT = 500


class ChatError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def places(game: Game) -> list[str]:
    """이 게임의 채팅 장소. 밀담 장소는 플레이어 둘이 한 쌍이 될 수 있도록 플레이어 수 ÷ 2(내림) 곳이다."""
    return [ALL_PLACE, *(f"밀담 {chr(ord('A') + i)}" for i in range(len(game.players) // 2))]


def occupants(game: Game, place: str) -> list[int]:
    return [a for a, p in game.chat_at.items() if p == place and a in game.players]


def move(game: Game, account_id: int, place: str) -> None:
    """플레이어가 장소를 옮긴다. 밀담 장소가 가득 차 있으면 들어갈 수 없다."""
    with game.lock:
        if account_id not in game.players:
            raise ChatError("not_player", "플레이어만 장소를 옮길 수 있습니다")
        if place not in places(game):
            raise ChatError("unknown", "없는 채팅 장소입니다")
        if game.chat_at.get(account_id) == place:
            return
        if place != ALL_PLACE and len(occupants(game, place)) >= SECRET_CAPACITY:
            raise ChatError("full", f"{place}은 이미 두 사람이 있습니다")
        game.chat_at[account_id] = place


def send(game: Game, conn, account_id: int, text: str) -> int:
    """지금 있는 장소에 메시지를 보낸다. 그 장소에 있는 플레이어(보낸 사람 포함)가 받는다."""
    text = text.strip()
    if not text:
        raise ChatError("empty", "보낼 내용을 적어 주세요")
    if len(text) > MAX_TEXT:
        raise ChatError("long", f"메시지는 {MAX_TEXT}자까지 보낼 수 있습니다")
    with game.lock:
        if account_id not in game.players:
            raise ChatError("not_player", "플레이어만 메시지를 보낼 수 있습니다")
        place = game.chat_at.get(account_id, ALL_PLACE)
        receivers = occupants(game, place)
        number = conn.execute(
            'INSERT INTO "대화" ("진행_번호", "계정_번호", "장소", "내용") VALUES (%s, %s, %s, %s) RETURNING "번호"',
            (game.id, account_id, place, text),
        ).fetchone()["번호"]
        for receiver in receivers:
            conn.execute('INSERT INTO "대화수신" ("대화_번호", "계정_번호") VALUES (%s, %s)', (number, receiver))
        return number


def view(game: Game, conn, viewer: int, after: int = 0) -> dict[str, Any]:
    """`viewer` 가 볼 수 있는 채팅: 장소와 사람들의 위치, 그리고 `after` 번호 뒤의 메시지."""
    with game.lock:
        player = game.players.get(viewer)
        observer = game.observers.get(viewer)
        if player is None and observer is None:
            raise KeyError(viewer)
        by_slot = {c["순서"]: c["이름"] for c in game.characters}
        who = {
            a: {"계정_번호": a, "닉네임": p.nickname, "인물_이름": by_slot.get(p.character)}
            for a, p in game.players.items()
        }
        rooms = [
            {"이름": place, "최대인원": None if place == ALL_PLACE else SECRET_CAPACITY,
             "사람들": [who[a] for a in occupants(game, place)]}
            for place in places(game)
        ]
        mine = game.chat_at.get(viewer) if player else None
        if player is not None:
            rows = conn.execute(
                'SELECT c."번호", c."장소", c."계정_번호", c."내용", c."보낸일시" FROM "대화" c '
                'JOIN "대화수신" r ON r."대화_번호" = c."번호" WHERE c."진행_번호" = %s AND r."계정_번호" = %s AND c."번호" > %s '
                'ORDER BY c."번호"', (game.id, viewer, after)).fetchall()
        elif observer.gm:
            rows = conn.execute(
                'SELECT "번호", "장소", "계정_번호", "내용", "보낸일시" FROM "대화" WHERE "진행_번호" = %s AND "번호" > %s ORDER BY "번호"',
                (game.id, after)).fetchall()
        else:
            rows = conn.execute(
                'SELECT "번호", "장소", "계정_번호", "내용", "보낸일시" FROM "대화" WHERE "진행_번호" = %s AND "장소" = %s AND "번호" > %s ORDER BY "번호"',
                (game.id, ALL_PLACE, after)).fetchall()
        sender = lambda a: who.get(a, {"계정_번호": a, "닉네임": "", "인물_이름": None})
        return {
            "내_위치": mine,
            "역할": "플레이어" if player else ("GM 관전" if observer.gm else "일반 관전"),
            "장소들": rooms,
            "메시지": [
                {"번호": r["번호"], "장소": r["장소"], "보낸이": sender(r["계정_번호"]), "내용": r["내용"], "보낸일시": r["보낸일시"]} for r in rows
            ],
        }


# ---- API -------------------------------------------------------------------------------

class ChatMemberOut(BaseModel):
    계정_번호: int
    닉네임: str
    인물_이름: str | None


class ChatRoomOut(BaseModel):
    이름: str
    최대인원: int | None
    사람들: list[ChatMemberOut]


class ChatMessageOut(BaseModel):
    번호: int
    장소: str
    보낸이: ChatMemberOut
    내용: str
    보낸일시: datetime


class ChatOut(BaseModel):
    내_위치: str | None
    역할: str
    장소들: list[ChatRoomOut]
    메시지: list[ChatMessageOut]


class ChatMoveIn(BaseModel):
    장소: str = Field(min_length=1, max_length=20)


class ChatSendIn(BaseModel):
    내용: str = Field(max_length=2000)


CHAT_STATUS = {
    "not_player": status.HTTP_403_FORBIDDEN,
    "unknown": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "full": status.HTTP_409_CONFLICT,
    "empty": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "long": status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def _game_of(request: Request, account_id: int) -> Game:
    from .game import _my_game
    return _my_game(request, account_id)


@router.get("", response_model=ChatOut)
def read_chat(conn: Conn, me: CurrentUser, request: Request, after: int = 0) -> dict:
    game = _game_of(request, me.계정.번호)
    return view(game, conn, me.계정.번호, after)


@router.post("/move", response_model=ChatOut)
def move_place(body: ChatMoveIn, conn: Conn, me: CurrentUser, request: Request) -> dict:
    game = _game_of(request, me.계정.번호)
    try:
        move(game, me.계정.번호, body.장소)
    except ChatError as err:
        raise HTTPException(CHAT_STATUS.get(err.code, status.HTTP_409_CONFLICT), err.message) from err
    return view(game, conn, me.계정.번호)


@router.post("/send", response_model=ChatOut)
def send_message(body: ChatSendIn, conn: Conn, me: CurrentUser, request: Request) -> dict:
    game = _game_of(request, me.계정.번호)
    try:
        send(game, conn, me.계정.번호, body.내용)
    except ChatError as err:
        raise HTTPException(CHAT_STATUS.get(err.code, status.HTTP_409_CONFLICT), err.message) from err
    return view(game, conn, me.계정.번호)
