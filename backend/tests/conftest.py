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


class Account:
    """테스트용 계정. headers 로 API 를 호출하고, 번호·아이디는 테스터 지정 등에 쓴다."""

    def __init__(self, headers: dict, number: int, login_id: str):
        self.headers, self.number, self.login_id = headers, number, login_id


@pytest.fixture
def make_account(client, test_dbname):
    """가입·로그인한 계정을 만든다. role 은 DB 에 직접 지정한다 (API 로는 올릴 수 없다)."""

    def make(role: str = "사용자") -> Account:
        uid = f"u{uuid.uuid4().hex[:10]}"
        res = client.post("/api/auth/signup", json={"아이디": uid, "패스워드": "password123", "닉네임": "제작자"})
        assert res.status_code == 201
        number = res.json()["번호"]
        if role != "사용자":
            with psycopg.connect(f"dbname={test_dbname}", autocommit=True) as conn:
                conn.execute('UPDATE "계정" SET "권한" = %s WHERE "번호" = %s', (role, number))
        token = client.post("/api/auth/login", json={"아이디": uid, "패스워드": "password123", "접속환경": "PC"}).json()["토큰"]
        return Account({"Authorization": f"Bearer {token}"}, number, uid)

    return make


@pytest.fixture
def new_user(make_account):
    """Authorization 헤더만 돌려주는 팩토리 (일반 사용자)."""
    return lambda: make_account().headers


@pytest.fixture
def headers(new_user):
    return new_user()


@pytest.fixture
def confirm(test_dbname):
    """작품에 확정 버전을 직접 만든다. 확정 기능이 아직 없어 DB 에 바로 넣는다 (시나리오 내용은 테스트와 무관)."""

    def make(work_id: int, version: str = "1.0") -> None:
        with psycopg.connect(f"dbname={test_dbname}", autocommit=True) as conn:
            conn.execute(
                'INSERT INTO "버전" ("작품_번호", "버전", "시나리오") VALUES (%s, %s, %s::jsonb)',
                (work_id, version, "{}"),
            )

    return make
