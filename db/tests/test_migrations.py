"""마이그레이션 적용 테스트 (요구사항 8, 9)."""
from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

import openpyxl

from helpers import MIGRATIONS_DIR, SPEC_PATH, Db, PgTestCase, admin_sql, migrate


def spec_table_names() -> list[str]:
    wb = openpyxl.load_workbook(SPEC_PATH, read_only=True)
    return [ws.title for ws in wb.worksheets if ws.title != "목차"]


class TestApplyOnEmptyDatabase(PgTestCase):
    """setUpClass 가 빈 DB 에 모든 마이그레이션을 적용한다. 여기서는 그 결과를 확인한다."""

    def test_all_spec_tables_created(self):
        created = {r[0] for r in self.db.rows(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename<>'schema_migrations'")}
        self.assertEqual(created, set(spec_table_names()))
        self.assertEqual(len(created), 31)

    def test_history_records_every_file(self):
        files = sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))
        recorded = [r[0] for r in self.db.rows("SELECT filename FROM schema_migrations ORDER BY filename")]
        self.assertEqual(recorded, files)

    def test_rerun_is_noop(self):
        self.assertEqual(migrate.run(self._dbname, MIGRATIONS_DIR), [])

    def test_table_names_are_korean_and_preserved(self):
        # 영문으로 바뀌거나 소문자화된 이름이 없어야 한다. 특히 "NPC" 의 대소문자.
        cols = {r[0] for r in self.db.rows(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema='public' AND table_name='인물'""")}
        self.assertIn("NPC", cols)
        self.assertNotIn("npc", cols)


class TestMigrationRunnerSafety(unittest.TestCase):
    def setUp(self):
        self.dbname = "mm_runner_" + uuid.uuid4().hex[:12]
        admin_sql(f'CREATE DATABASE "{self.dbname}"')
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Db(self.dbname)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        admin_sql(f'DROP DATABASE IF EXISTS "{self.dbname}" WITH (FORCE)')

    def test_failed_migration_rolls_back_whole_file(self):
        (self.tmp / "0001_ok.sql").write_text('CREATE TABLE "가" ("번호" INTEGER);', encoding="utf-8")
        (self.tmp / "0002_bad.sql").write_text(
            'CREATE TABLE "나" ("번호" INTEGER);\nCREATE TABLE "다" (broken syntax here);', encoding="utf-8")
        with self.assertRaises(migrate.MigrationError):
            migrate.run(self.dbname, self.tmp)
        tables = {r[0] for r in self.db.rows(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'")}
        self.assertIn("가", tables)        # 앞 파일은 적용됨
        self.assertNotIn("나", tables)     # 실패한 파일은 일부도 남지 않음
        recorded = [r[0] for r in self.db.rows("SELECT filename FROM schema_migrations")]
        self.assertEqual(recorded, ["0001_ok.sql"])

    def test_modified_applied_migration_is_rejected(self):
        f = self.tmp / "0001_ok.sql"
        f.write_text('CREATE TABLE "가" ("번호" INTEGER);', encoding="utf-8")
        migrate.run(self.dbname, self.tmp)
        f.write_text('CREATE TABLE "가" ("번호" INTEGER, "x" TEXT);', encoding="utf-8")
        with self.assertRaises(migrate.MigrationError) as cm:
            migrate.run(self.dbname, self.tmp)
        self.assertIn("체크섬", str(cm.exception))

    def test_invalid_filename_is_rejected(self):
        (self.tmp / "create_tables.sql").write_text("SELECT 1;", encoding="utf-8")
        with self.assertRaises(migrate.MigrationError):
            migrate.run(self.dbname, self.tmp)


if __name__ == "__main__":
    unittest.main()
