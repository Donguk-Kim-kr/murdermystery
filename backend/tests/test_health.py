import psycopg

from app.db import get_conn
from app.main import app


def test_health_ok(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "database": "ok"}


def test_pool_uses_migrated_schema(client):
    # 풀이 마이그레이션이 적용된 DB에 연결되어 있고 한글 테이블을 조회할 수 있어야 한다.
    with client.app.state.pool.connection() as conn:
        row = conn.execute('SELECT count(*) AS n FROM "계정"').fetchone()
    assert row["n"] == 0


def test_health_returns_503_when_database_fails(client):
    class BrokenConn:
        def execute(self, *a, **kw):
            raise psycopg.OperationalError("연결 끊김")

    app.dependency_overrides[get_conn] = lambda: BrokenConn()
    try:
        res = client.get("/api/health")
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 503
