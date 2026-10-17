import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from psycopg import Error

from .auth import router as auth_router
from .characters import router as characters_router
from .config import get_settings
from .confirm import router as confirm_router
from .content import router as content_router, schema_router as content_schema_router
from .db import Conn, create_pool
from .library import router as library_router
from .phases import router as phases_router
from .play import router as play_router
from .publishing import router as publishing_router
from .roomstate import JoinLimiter, RoomRegistry
from .engine import GameRegistry
from .game import router as game_router, state_router as game_state_router
from .rooms import expire_rooms, router as rooms_router
from .static import mount_frontend
from .testers import router as testers_router
from .works import router as works_router


def sweep_rooms(app: FastAPI) -> None:
    """만료된 방을 종료하고, 이미 닫힌 방의 대기실을 메모리에서 지운다."""
    with app.state.pool.connection() as conn:
        for room_id in expire_rooms(conn):
            app.state.rooms.remove_room(room_id)
            app.state.games.remove(room_id)
        open_ids = app.state.rooms.room_ids()
        if open_ids:
            alive = {
                r["번호"]
                for r in conn.execute(
                    'SELECT "번호" FROM "방" WHERE "번호" = ANY(%s) AND "상태" <> \'종료\'', (open_ids,)
                ).fetchall()
            }
            for room_id in open_ids:
                if room_id not in alive:
                    app.state.rooms.remove_room(room_id)
                    app.state.games.remove(room_id)


async def sweep_loop(app: FastAPI, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await run_in_threadpool(sweep_rooms, app)
        except Exception:  # 정리 작업의 실패가 서버를 멈추면 안 된다. 다음 주기에 다시 한다.
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    pool = create_pool(settings)
    pool.open(wait=True, timeout=10)
    app.state.pool = pool
    app.state.rooms = RoomRegistry(settings.room_member_timeout_seconds)
    app.state.games = GameRegistry()
    app.state.join_limiter = JoinLimiter(settings.room_join_fail_limit, settings.room_join_fail_window_seconds)
    sweeper = asyncio.create_task(sweep_loop(app, settings.room_sweep_seconds))
    try:
        yield
    finally:
        sweeper.cancel()
        pool.close()


app = FastAPI(title="머더미스터리 플랫폼", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(works_router)
app.include_router(characters_router)
app.include_router(content_schema_router)
app.include_router(content_router)
app.include_router(phases_router)
app.include_router(play_router)
app.include_router(library_router)
app.include_router(confirm_router)
app.include_router(publishing_router)
app.include_router(testers_router)
app.include_router(rooms_router)
app.include_router(game_router)
app.include_router(game_state_router)


@app.get("/api/health")
def health(conn: Conn) -> dict[str, str]:
    try:
        conn.execute("SELECT 1")
    except Error as exc:
        raise HTTPException(status_code=503, detail="데이터베이스에 연결할 수 없습니다") from exc
    return {"status": "ok", "database": "ok"}


# 화면 서비스는 모든 API 경로를 등록한 뒤 마지막에 붙인다. (먼저 붙이면 "/" 아래의 모든 경로를 가로챈다)
if get_settings().static_dir:
    mount_frontend(app, get_settings().static_dir)
