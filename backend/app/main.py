from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from psycopg import Connection, Error

from .config import get_settings
from .db import create_pool, get_conn


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


@app.get("/api/health")
def health(conn: Connection = Depends(get_conn)) -> dict[str, str]:
    try:
        conn.execute("SELECT 1")
    except Error as exc:
        raise HTTPException(status_code=503, detail="데이터베이스에 연결할 수 없습니다") from exc
    return {"status": "ok", "database": "ok"}
