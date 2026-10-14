from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from psycopg import Error

from .auth import router as auth_router
from .config import get_settings
from .db import Conn, create_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = create_pool(get_settings())
    pool.open(wait=True, timeout=10)
    app.state.pool = pool
    try:
        yield
    finally:
        pool.close()


app = FastAPI(title="머더미스터리 플랫폼", lifespan=lifespan)
app.include_router(auth_router)


@app.get("/api/health")
def health(conn: Conn) -> dict[str, str]:
    try:
        conn.execute("SELECT 1")
    except Error as exc:
        raise HTTPException(status_code=503, detail="데이터베이스에 연결할 수 없습니다") from exc
    return {"status": "ok", "database": "ok"}
