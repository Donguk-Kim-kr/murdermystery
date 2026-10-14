"""DB 테스트 공통 헬퍼 (표준 라이브러리 + psql 만 사용).

접속 정보는 libpq 표준 환경변수(PGHOST, PGPORT, PGUSER, PGPASSWORD)를 따른다.
테스트 클래스마다 임시 데이터베이스를 새로 만들어 모든 마이그레이션을 적용하고, 끝나면 삭제한다.
"""
from __future__ import annotations

import itertools
import os
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# MM_MIGRATIONS_DIR 로 다른 디렉터리를 지정할 수 있다. (테스트가 실제로 불일치를 잡는지 확인하는 용도)
MIGRATIONS_DIR = Path(os.environ["MM_MIGRATIONS_DIR"]) if os.environ.get("MM_MIGRATIONS_DIR") else ROOT / "migrations"
SPEC_PATH = ROOT / "spec" / "schema_spec.xlsx"
sys.path.insert(0, str(ROOT / "scripts"))

import migrate  # noqa: E402  (db/scripts/migrate.py)


def _psql(dbname: str, sql: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["psql", "-X", "-q", "-A", "-t", "-F", "|", "-v", "ON_ERROR_STOP=1", "-d", dbname, "-f", "-"],
        input=sql, capture_output=True, text=True,
    )


def admin_sql(sql: str) -> None:
    proc = _psql("postgres", sql)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)


class Db:
    """한 데이터베이스에 대한 얇은 psql 래퍼."""

    def __init__(self, dbname: str):
        self.dbname = dbname
        self._seq = itertools.count(1)

    def run(self, sql: str) -> subprocess.CompletedProcess:
        return _psql(self.dbname, sql)

    def ok(self, sql: str) -> str:
        """성공해야 하는 SQL. 표준 출력을 돌려준다."""
        proc = self.run(sql)
        if proc.returncode != 0:
            raise AssertionError(f"SQL 실패:\n{sql}\n--- stderr ---\n{proc.stderr}")
        return proc.stdout.strip()

    def fails(self, sql: str, contains: str | None = None) -> str:
        """실패해야 하는 SQL. 오류 메시지를 돌려준다."""
        proc = self.run(sql)
        if proc.returncode == 0:
            raise AssertionError(f"실패해야 하는 SQL 이 성공했습니다:\n{sql}")
        if contains is not None and contains not in proc.stderr:
            raise AssertionError(
                f"오류 메시지에 {contains!r} 가 없습니다.\nSQL:\n{sql}\n--- stderr ---\n{proc.stderr}"
            )
        return proc.stderr

    def rows(self, sql: str) -> list[list[str]]:
        out = self.ok(sql)
        return [line.split("|") for line in out.splitlines() if line != ""]

    def val(self, sql: str) -> str:
        return self.ok(sql)

    def n(self) -> int:
        return next(self._seq)


class PgTestCase(unittest.TestCase):
    """클래스마다 새 DB 를 만들고, 테스트마다 모든 데이터를 비운다."""

    db: Db
    _dbname: str

    @classmethod
    def setUpClass(cls) -> None:
        cls._dbname = "mm_test_" + uuid.uuid4().hex[:12]
        admin_sql(f'CREATE DATABASE "{cls._dbname}"')
        try:
            migrate.run(cls._dbname, MIGRATIONS_DIR)
        except Exception:
            admin_sql(f'DROP DATABASE IF EXISTS "{cls._dbname}" WITH (FORCE)')
            raise
        cls.db = Db(cls._dbname)
        tables = [r[0] for r in cls.db.rows(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename<>'schema_migrations'"
        )]
        cls._truncate_sql = "TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"

    @classmethod
    def tearDownClass(cls) -> None:
        admin_sql(f'DROP DATABASE IF EXISTS "{cls._dbname}" WITH (FORCE)')

    def setUp(self) -> None:
        self.db.ok(self._truncate_sql)

    # ---- 시드 데이터 빌더 -------------------------------------------------
    def account(self, status: str = "정상") -> int:
        k = self.db.n()
        return int(self.db.val(
            f"""INSERT INTO "계정"("아이디","패스워드","닉네임","상태")
                VALUES ('user{k}','hash{k}','닉{k}','{status}') RETURNING "번호" """
        ))

    def work(self, account: int | None = None) -> int:
        account = account or self.account()
        k = self.db.n()
        return int(self.db.val(
            f"""INSERT INTO "작품"("제목","시놉시스","장르","계정_번호")
                VALUES ('작품{k}','시놉시스','추리',{account}) RETURNING "번호" """
        ))

    def sql_id(self, sql: str) -> int:
        return int(self.db.val(sql))
