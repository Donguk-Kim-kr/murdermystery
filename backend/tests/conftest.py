"""임시 데이터베이스를 만들어 모든 마이그레이션을 적용한 뒤 앱을 그 DB에 연결한다.

접속 정보는 libpq 표준 환경변수(PGHOST, PGPORT, PGUSER, PGPASSWORD)를 따른다. CREATEDB 권한이 필요하다.
"""
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

DB_DIR = Path(__file__).resolve().parents[2] / "db"
sys.path.insert(0, str(DB_DIR / "scripts"))

import migrate  # noqa: E402  (db/scripts/migrate.py)

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def test_dbname():
    name = f"mm_api_test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect("dbname=postgres", autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    try:
        migrate.run(name, DB_DIR / "migrations")
        yield name
    finally:
        with psycopg.connect("dbname=postgres", autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture(scope="session")
def client(test_dbname):
    mp = pytest.MonkeyPatch()
    mp.setenv("MM_DATABASE_URL", f"dbname={test_dbname}")
    get_settings.cache_clear()
    try:
        with TestClient(app) as c:
            yield c
    finally:
        mp.undo()
        get_settings.cache_clear()


@pytest.fixture
def new_user(client):
    """가입·로그인한 새 사용자의 Authorization 헤더를 돌려주는 팩토리."""

    def make() -> dict:
        uid = f"u{uuid.uuid4().hex[:10]}"
        assert client.post("/api/auth/signup", json={"아이디": uid, "패스워드": "password123", "닉네임": "제작자"}).status_code == 201
        res = client.post("/api/auth/login", json={"아이디": uid, "패스워드": "password123", "접속환경": "PC"})
        return {"Authorization": f"Bearer {res.json()['토큰']}"}

    return make


@pytest.fixture
def headers(new_user):
    return new_user()
