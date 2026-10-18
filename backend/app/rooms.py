"""방 API (docs/DB_RULES.md B37·B38).

* 1방 1게임: 방을 만들 때 작품을 고르고, 그 작품의 **확정된 최신 버전**이 방에 저장된다.
* 입장은 입장코드를 아는 사람이면 된다(작품 공개 여부와 무관). 코드를 알려 주는 것은 방장의 선택이다.
* 방을 만들 수 있는 사람: 공개 작품은 누구나, 비공개 작품은 제작자와 테스터(비공개 플레이)뿐이다.
* 한 계정은 한 번에 한 방에만 있을 수 있다. 방장은 플레이어로 참여할지 선택한다.
* 대기실의 입장자 목록은 DB 가 아니라 메모리에 있다(`roomstate.py`). 이 단계에는 배역 선택과 게임 시작이 없다
  (확정 스냅샷 형식이 정해져야 만들 수 있다).
"""
import secrets
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from psycopg import Connection
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field, field_validator

from .auth import CurrentSession, CurrentUser
from .db import Conn
from .engine import Observer
from .roomstate import JoinLimiter, RoomError, RoomRegistry, WaitingRoom
from .testers import can_private_play

router = APIRouter(prefix="/api/rooms", tags=["rooms"])

# 입장코드는 방장이 정한다(비우면 헷갈리는 글자(I, O, 0, 1)를 뺀 32자 6칸을 무작위로 만든다). 종료되지 않은 방끼리만 유일하고 종료된 방의 코드는 다시 쓸 수 있다(0022).
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6

ERROR_STATUS = {
    "in_other_room": status.HTTP_409_CONFLICT,
    "full": status.HTTP_409_CONFLICT,
    "closed": status.HTTP_404_NOT_FOUND,
}


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


# ---- 모델 -------------------------------------------------------------------------------

CODE_MIN_LENGTH = 4
CODE_MAX_LENGTH = 10
# 방장이 정하는 입장코드의 글자: 영문(대문자로 바꿈)·숫자·한글. 공백과 기호는 쓰지 않는다.
CODE_PATTERN = r"^[A-Z0-9가-힣]+$"


class RoomCreateIn(BaseModel):
    작품_번호: int
    방장_참여: bool = True
    # 방장이 정하는 입장코드. 비우면 서버가 무작위로 만든다.
    입장코드: str | None = Field(default=None, min_length=CODE_MIN_LENGTH, max_length=CODE_MAX_LENGTH, pattern=CODE_PATTERN)

    @field_validator("입장코드", mode="before")
    @classmethod
    def normalize_code(cls, value):
        if isinstance(value, str):
            value = value.strip().upper()
            return value or None                     # 빈 칸은 "자동으로 만들기"
        return value


class JoinIn(BaseModel):
    입장코드: str = Field(min_length=1, max_length=20)
    # 관전자로 들어간다: 진행 중인 방(플레이어로는 못 들어간다)이나 자리가 가득 찬 대기실에서 쓴다
    관전: bool = False


class ParticipationIn(BaseModel):
    플레이: bool | None = None
    GM관전: bool | None = None
    # 방장이 다른 사람을 옮길 때만 쓴다. 비우면 나 자신
    계정_번호: int | None = None


class MemberOut(BaseModel):
    계정_번호: int
    닉네임: str
    방장: bool
    플레이: bool
    GM관전: bool


class RoomWorkOut(BaseModel):
    번호: int
    제목: str
    시놉시스: str
    장르: str
    예상시간: str
    최소인원: int
    최대인원: int


class RoomOut(BaseModel):
    번호: int
    입장코드: str
    상태: str
    작품: RoomWorkOut
    버전: str
    내가_방장: bool
    내_계정_번호: int
    참가자: list[MemberOut]
    플레이어_수: int
    게임_종료: bool = False   # 진행 중인 방에서 게임이 끝났다(방은 그로부터 6시간 뒤에 닫힌다)
    생성일시: datetime


# ---- 도우미 -----------------------------------------------------------------------------

def registry(request: Request) -> RoomRegistry:
    return request.app.state.rooms


def limiter(request: Request) -> JoinLimiter:
    return request.app.state.join_limiter


def raise_room_error(err: RoomError) -> None:
    raise HTTPException(ERROR_STATUS.get(err.code, status.HTTP_409_CONFLICT), err.message)


ROOM_SELECT = (
    'SELECT r."번호", r."입장코드", r."상태", r."버전_버전", r."계정_번호" AS 방장, r."생성일시", '
    'w."번호" AS 작품_번호, w."제목", w."시놉시스", w."장르", w."예상시간", w."최소인원", w."최대인원" '
    'FROM "방" r JOIN "작품" w ON w."번호" = r."작품_번호" '
)


def expire_rooms(conn: Connection) -> list[int]:
    """오래된 방을 종료한다 (B25: 대기 6시간, 진행 12시간 상한. 게임이 끝났으면 그로부터 6시간 뒤). 종료일시는 DB 트리거가 기록한다."""
    rows = conn.execute(
        """
        UPDATE "방" SET "상태" = '종료'
        WHERE ("상태" = '대기' AND "상태변경일시" < CURRENT_TIMESTAMP - interval '6 hours')
           OR ("상태" = '진행' AND "상태변경일시" < CURRENT_TIMESTAMP - interval '12 hours')
           OR ("상태" = '진행' AND EXISTS (
                SELECT 1 FROM "진행" g
                WHERE g."방_번호" = "방"."번호" AND g."상태" = '종료' AND g."종료일시" < CURRENT_TIMESTAMP - interval '6 hours'))
        RETURNING "번호"
        """
    ).fetchall()
    return [r["번호"] for r in rows]


def expire_stale(request: Request) -> None:
    """만료된 방을 종료한다. 요청의 트랜잭션과 **별개로 즉시 커밋**한다.

    요청이 입장 거부 같은 오류로 끝나면 그 트랜잭션은 롤백되므로, 같은 트랜잭션에서 하면 만료 처리가 함께 취소된다.
    """
    with request.app.state.pool.connection() as separate:
        expired = expire_rooms(separate)
    for room_id in expired:
        registry(request).remove_room(room_id)
        request.app.state.games.remove(room_id)


def build_room_out(row: dict, room: WaitingRoom, me_id: int, game_ended: bool = False) -> RoomOut:
    members = [
        MemberOut(계정_번호=m.account_id, 닉네임=m.nickname, 방장=m.account_id == room.host_id, 플레이=m.playing, GM관전=m.gm)
        for m in sorted(room.members.values(), key=lambda m: (m.account_id != room.host_id, m.account_id))
    ]
    return RoomOut(
        번호=row["번호"], 입장코드=row["입장코드"], 상태=row["상태"],
        작품=RoomWorkOut(
            번호=row["작품_번호"], 제목=row["제목"], 시놉시스=row["시놉시스"], 장르=row["장르"],
            예상시간=row["예상시간"], 최소인원=row["최소인원"], 최대인원=row["최대인원"],
        ),
        버전=row["버전_버전"], 내가_방장=room.host_id == me_id, 내_계정_번호=me_id, 참가자=members,
        플레이어_수=room.player_count(), 게임_종료=game_ended, 생성일시=row["생성일시"],
    )


def find_my_room(conn: Connection, reg: RoomRegistry, me: CurrentSession) -> tuple[dict, WaitingRoom] | None:
    """내가 지금 있는 방. 대기실에 있거나, 서버 재시작 전에 만든 내 방(DB)이면 복원한다."""
    room = reg.room_of(me.계정.번호)
    if room is not None:
        row = conn.execute(ROOM_SELECT + 'WHERE r."번호" = %s', (room.room_id,)).fetchone()
        if row is None or row["상태"] == "종료":
            reg.remove_room(room.room_id)
            return None
        return row, room
    row = conn.execute(
        ROOM_SELECT + 'WHERE r."계정_번호" = %s AND r."상태" IN (\'대기\', \'진행\') ORDER BY r."번호" DESC LIMIT 1',
        (me.계정.번호,),
    ).fetchone()
    if row is None:
        return None
    # 방장이 서버 재시작 뒤에 돌아왔다. 입장자는 사라졌고, 방장은 플레이어로 복원한다.
    room = reg.open_room(row["번호"], row["입장코드"], me.계정.번호, me.계정.닉네임, True)
    return row, room


def lock_account(conn: Connection, account_id: int) -> None:
    """같은 계정의 방 만들기·입장이 동시에 들어와도 한 번에 하나씩 처리한다."""
    conn.execute("SELECT pg_advisory_xact_lock(%s, %s)", (7001, account_id))


# ---- 엔드포인트 ----------------------------------------------------------------------------

@router.post("", status_code=status.HTTP_201_CREATED, response_model=RoomOut)
def create_room(body: RoomCreateIn, conn: Conn, me: CurrentUser, request: Request) -> RoomOut:
    reg = registry(request)
    expire_stale(request)
    lock_account(conn, me.계정.번호)
    if find_my_room(conn, reg, me) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 참여 중인 방이 있습니다.")

    work = conn.execute(
        'SELECT "번호", "계정_번호", "공개여부", "공개권한" FROM "작품" WHERE "번호" = %s AND "상태" <> \'삭제\'', (body.작품_번호,)
    ).fetchone()
    if work is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "작품을 찾을 수 없습니다")
    if not work["공개여부"] and not can_private_play(conn, me.계정.번호, work["번호"]):
        related = work["계정_번호"] == me.계정.번호 or conn.execute(
            'SELECT 1 FROM "테스터" WHERE "작품_번호" = %s AND "계정_번호" = %s', (work["번호"], me.계정.번호)
        ).fetchone()
        if not related:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "작품을 찾을 수 없습니다")  # 비공개 작품의 존재를 알리지 않는다
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "관리자·운영자가 비공개한 작품은 공개 권한이 제작자에게 돌아올 때까지 방을 만들 수 없습니다",
        )
    version = conn.execute(
        'SELECT "버전" FROM "버전" WHERE "작품_번호" = %s ORDER BY "번호" DESC LIMIT 1', (work["번호"],)
    ).fetchone()
    if version is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "확정된 버전이 없는 작품으로는 방을 만들 수 없습니다")

    insert = (
        'INSERT INTO "방" ("계정_번호", "입장코드", "작품_번호", "버전_버전") VALUES (%s, %s, %s, %s) RETURNING "번호"'
    )
    if body.입장코드:
        code = body.입장코드                          # 방장이 정한 코드. 종료되지 않은 방이 이미 쓰고 있으면 거절한다
        try:
            with conn.transaction():
                created = conn.execute(insert, (me.계정.번호, code, work["번호"], version["버전"])).fetchone()
        except UniqueViolation:
            raise HTTPException(status.HTTP_409_CONFLICT, "이미 사용 중인 입장코드입니다. 다른 코드를 정해 주세요") from None
    else:
        for _ in range(10):  # 무작위 코드가 겹치면 다시 뽑는다
            code = new_code()
            try:
                with conn.transaction():
                    created = conn.execute(insert, (me.계정.번호, code, work["번호"], version["버전"])).fetchone()
                break
            except UniqueViolation:
                continue
        else:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "입장코드를 만들지 못했습니다. 다시 시도해 주세요")

    room = reg.open_room(created["번호"], code, me.계정.번호, me.계정.닉네임, body.방장_참여)
    row = conn.execute(ROOM_SELECT + 'WHERE r."번호" = %s', (created["번호"],)).fetchone()
    return build_room_out(row, room, me.계정.번호)


ROOM_IN_PROGRESS = "진행 중인 방입니다."


def join_as_observer(conn: Connection, request: Request, row: dict, me: CurrentSession) -> RoomOut:
    """진행 중인 방에 관전자로 들어간다. 관전자는 모두에게 공개된 내용만 본다."""
    reg = registry(request)
    game = request.app.state.games.get(row["번호"])
    if game is None or reg.get(row["번호"]) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, ROOM_IN_PROGRESS)
    try:
        room = reg.join_observer(row["번호"], me.계정.번호, me.계정.닉네임)
    except RoomError as err:
        raise_room_error(err)
    with game.lock:
        if me.계정.번호 not in game.players and me.계정.번호 not in game.observers:
            game.observers[me.계정.번호] = Observer(me.계정.번호, me.계정.닉네임)
            game.last_seen[me.계정.번호] = game.clock()
            game.bump()
    return build_room_out(row, room, me.계정.번호)


@router.post("/join", response_model=RoomOut)
def join_room(body: JoinIn, conn: Conn, me: CurrentUser, request: Request) -> RoomOut:
    reg, lim = registry(request), limiter(request)
    if lim.blocked(me.계정.번호):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "잠시 뒤에 다시 시도해 주세요.")
    expire_stale(request)
    lock_account(conn, me.계정.번호)
    # 종료된 방의 코드는 다시 쓰일 수 있으므로 종료되지 않은 방만 찾는다(그런 방은 코드마다 하나뿐이다).
    row = conn.execute(
        ROOM_SELECT + 'WHERE r."입장코드" = %s AND r."상태" <> \'종료\'', (body.입장코드.strip().upper(),)
    ).fetchone()
    if row is None:
        lim.record_failure(me.계정.번호)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "입장코드가 올바르지 않습니다")
    lim.reset(me.계정.번호)

    mine = find_my_room(conn, reg, me)
    if mine is not None and mine[0]["번호"] != row["번호"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "다른 방에 참여 중입니다.")
    if mine is not None:                                  # 이미 이 방에 있다(다시 코드를 넣었다): 그대로 돌려준다
        return build_room_out(mine[0], mine[1], me.계정.번호)
    if row["상태"] != "대기":
        if row["상태"] == "진행" and body.관전:
            return join_as_observer(conn, request, row, me)
        raise HTTPException(status.HTTP_409_CONFLICT, ROOM_IN_PROGRESS)
    if reg.get(row["번호"]) is None:  # 서버 재시작 등으로 대기실이 사라졌고, 방장이 돌아오면 DB 로 복원된다
        raise HTTPException(status.HTTP_409_CONFLICT, "방장이 아직 대기실에 돌아오지 않았습니다. 잠시 뒤에 다시 시도해 주세요")
    try:
        room = reg.join(row["번호"], me.계정.번호, me.계정.닉네임, row["최대인원"], observe=body.관전)
    except RoomError as err:
        raise_room_error(err)
    return build_room_out(row, room, me.계정.번호)


@router.get("/me", response_model=RoomOut | None)
def my_room(conn: Conn, me: CurrentUser, request: Request) -> RoomOut | None:
    """내가 있는 방의 현재 상태. 대기실 화면이 2~3초마다 부르며, 이 호출이 입장 유지 신호(하트비트)도 겸한다."""
    reg = registry(request)
    mine = find_my_room(conn, reg, me)
    if mine is None:
        return None
    row, room = mine
    reg.touch(me.계정.번호)
    game = request.app.state.games.get(row["번호"])
    return build_room_out(row, room, me.계정.번호, game_ended=game is not None and game.ended)


@router.patch("/me", response_model=RoomOut)
def set_participation(body: ParticipationIn, conn: Conn, me: CurrentUser, request: Request) -> RoomOut:
    """참여/관전 자리를 옮긴다. 자기 자리는 누구나, 다른 사람의 자리는 방장만 옮긴다. GM 관전 여부는 본인만 고른다."""
    reg = registry(request)
    mine = find_my_room(conn, reg, me)
    if mine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "참여 중인 방이 없습니다")
    row, room = mine
    if row["상태"] != "대기":
        raise HTTPException(status.HTTP_409_CONFLICT, ROOM_IN_PROGRESS)
    target = body.계정_번호 if body.계정_번호 is not None else me.계정.번호
    if target != me.계정.번호 and room.host_id != me.계정.번호:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "방장만 다른 사람을 옮길 수 있습니다")
    if target not in room.members:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "방에 없는 사람입니다")
    if body.GM관전 is not None and target != me.계정.번호:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "관전 방식은 본인만 고를 수 있습니다")
    try:
        if body.플레이 is not None:
            reg.set_playing(row["번호"], target, body.플레이, row["최대인원"])
        if body.GM관전 is not None:
            reg.set_gm(row["번호"], target, body.GM관전)
    except RoomError as err:
        raise_room_error(err)
    return build_room_out(row, room, me.계정.번호)


@router.post("/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_room(conn: Conn, me: CurrentUser, request: Request) -> None:
    """방에서 나간다. 방장이 나가면 방이 닫힌다."""
    reg = registry(request)
    mine = find_my_room(conn, reg, me)
    if mine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "참여 중인 방이 없습니다")
    row, room = mine
    if room.host_id == me.계정.번호:
        if row["상태"] != "대기":
            raise HTTPException(status.HTTP_409_CONFLICT, "진행 중인 방은 나갈 수 없습니다")
        conn.execute('UPDATE "방" SET "상태" = \'종료\' WHERE "번호" = %s', (row["번호"],))
        reg.remove_room(row["번호"])
    else:
        reg.leave(me.계정.번호)
        game = request.app.state.games.get(row["번호"])
        if game is not None:
            with game.lock:                                   # 관전자가 나가면 게임의 관전자 목록에서도 뺀다
                if game.observers.pop(me.계정.번호, None) is not None:
                    game.last_seen.pop(me.계정.번호, None)
                    game.bump()
