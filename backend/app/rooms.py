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
from pydantic import BaseModel, Field

from .auth import CurrentSession, CurrentUser
from .db import Conn
from .roomstate import JoinLimiter, RoomError, RoomRegistry, WaitingRoom
from .testers import can_private_play

router = APIRouter(prefix="/api/rooms", tags=["rooms"])

# 입장코드: 헷갈리는 글자(I, O, 0, 1)를 뺀 32자 6칸. 방은 종료돼도 코드가 DB 에 남아 재사용되지 않는다(UNIQUE).
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

class RoomCreateIn(BaseModel):
    작품_번호: int
    방장_참여: bool = True


class JoinIn(BaseModel):
    입장코드: str = Field(min_length=1, max_length=20)


class ParticipationIn(BaseModel):
    플레이: bool


class MemberOut(BaseModel):
    계정_번호: int
    닉네임: str
    방장: bool
    플레이: bool


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
    참가자: list[MemberOut]
    플레이어_수: int
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
    """오래된 방을 종료한다 (B25: 대기 6시간, 진행 12시간). 종료일시는 DB 트리거가 기록한다."""
    rows = conn.execute(
        """
        UPDATE "방" SET "상태" = '종료'
        WHERE ("상태" = '대기' AND "상태변경일시" < CURRENT_TIMESTAMP - interval '6 hours')
           OR ("상태" = '진행' AND "상태변경일시" < CURRENT_TIMESTAMP - interval '12 hours')
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


def build_room_out(row: dict, room: WaitingRoom, me_id: int) -> RoomOut:
    members = [
        MemberOut(계정_번호=m.account_id, 닉네임=m.nickname, 방장=m.account_id == room.host_id, 플레이=m.playing)
        for m in sorted(room.members.values(), key=lambda m: (m.account_id != room.host_id, m.account_id))
    ]
    return RoomOut(
        번호=row["번호"], 입장코드=row["입장코드"], 상태=row["상태"],
        작품=RoomWorkOut(
            번호=row["작품_번호"], 제목=row["제목"], 시놉시스=row["시놉시스"], 장르=row["장르"],
            예상시간=row["예상시간"], 최소인원=row["최소인원"], 최대인원=row["최대인원"],
        ),
        버전=row["버전_버전"], 내가_방장=room.host_id == me_id, 참가자=members,
        플레이어_수=room.player_count(), 생성일시=row["생성일시"],
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
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 참여 중인 방이 있습니다. 먼저 나가 주세요")

    work = conn.execute(
        'SELECT "번호", "계정_번호", "공개여부", "공개권한" FROM "작품" WHERE "번호" = %s', (body.작품_번호,)
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

    for _ in range(10):  # 코드가 겹치면 다시 뽑는다
        code = new_code()
        try:
            with conn.transaction():
                created = conn.execute(
                    'INSERT INTO "방" ("계정_번호", "입장코드", "작품_번호", "버전_버전") VALUES (%s, %s, %s, %s) '
                    'RETURNING "번호"',
                    (me.계정.번호, code, work["번호"], version["버전"]),
                ).fetchone()
            break
        except UniqueViolation:
            continue
    else:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "입장코드를 만들지 못했습니다. 다시 시도해 주세요")

    room = reg.open_room(created["번호"], code, me.계정.번호, me.계정.닉네임, body.방장_참여)
    row = conn.execute(ROOM_SELECT + 'WHERE r."번호" = %s', (created["번호"],)).fetchone()
    return build_room_out(row, room, me.계정.번호)


@router.post("/join", response_model=RoomOut)
def join_room(body: JoinIn, conn: Conn, me: CurrentUser, request: Request) -> RoomOut:
    reg, lim = registry(request), limiter(request)
    if lim.blocked(me.계정.번호):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "입장코드를 너무 많이 틀렸습니다. 잠시 뒤에 다시 시도해 주세요")
    expire_stale(request)
    lock_account(conn, me.계정.번호)
    row = conn.execute(ROOM_SELECT + 'WHERE r."입장코드" = %s', (body.입장코드.strip().upper(),)).fetchone()
    if row is None:
        lim.record_failure(me.계정.번호)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "입장코드가 올바르지 않습니다")
    if row["상태"] != "대기":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 시작했거나 종료된 방입니다")
    lim.reset(me.계정.번호)

    mine = find_my_room(conn, reg, me)
    if mine is not None and mine[0]["번호"] != row["번호"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 다른 방에 참여 중입니다. 먼저 나가 주세요")
    if reg.get(row["번호"]) is None:  # 서버 재시작 등으로 대기실이 사라졌고, 방장이 돌아오면 DB 로 복원된다
        raise HTTPException(status.HTTP_409_CONFLICT, "방장이 아직 대기실에 돌아오지 않았습니다. 잠시 뒤에 다시 시도해 주세요")
    try:
        room = reg.join(row["번호"], me.계정.번호, me.계정.닉네임, row["최대인원"])
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
    return build_room_out(row, room, me.계정.번호)


@router.patch("/me", response_model=RoomOut)
def set_participation(body: ParticipationIn, conn: Conn, me: CurrentUser, request: Request) -> RoomOut:
    """방장이 플레이어로 참여할지 바꾼다."""
    reg = registry(request)
    mine = find_my_room(conn, reg, me)
    if mine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "참여 중인 방이 없습니다")
    row, room = mine
    if room.host_id != me.계정.번호:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "방장만 바꿀 수 있습니다")
    try:
        reg.set_playing(row["번호"], me.계정.번호, body.플레이, row["최대인원"])
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
