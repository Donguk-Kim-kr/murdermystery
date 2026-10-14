#!/usr/bin/env python3
"""마이그레이션 실행기 (표준 라이브러리 + psql 만 사용).

사용법:
    python3 db/scripts/migrate.py --dbname murder_mystery
    python3 db/scripts/migrate.py --dbname murder_mystery --dir db/migrations

접속 정보는 libpq 표준 환경변수(PGHOST, PGPORT, PGUSER, PGPASSWORD)를 따른다.

동작:
  * db/migrations/NNNN_*.sql 을 파일명 순서대로 적용한다.
  * 각 파일은 하나의 트랜잭션으로 적용되며, 실패하면 해당 파일 전체가 롤백되고 중단된다.
  * 적용 이력은 schema_migrations 테이블에 파일명과 SHA-256 체크섬으로 기록한다.
  * 이미 적용된 파일은 다시 실행하지 않는다.
  * 이미 적용된 파일의 내용이 바뀌었으면(체크섬 불일치) 오류로 중단한다.
    적용된 마이그레이션은 수정하지 말고 새 파일을 추가해야 한다.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

FILENAME_RE = re.compile(r"^\d{4}_[A-Za-z0-9_]+\.sql$")


class MigrationError(Exception):
    pass


def psql(dbname: str, *args: str, capture: bool = False) -> str:
    cmd = ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", dbname, *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MigrationError(proc.stderr.strip() or f"psql 종료 코드 {proc.returncode}")
    return proc.stdout if capture else ""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_history_table(dbname: str) -> None:
    psql(
        dbname,
        "-c",
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               filename   TEXT PRIMARY KEY,
               checksum   TEXT NOT NULL,
               applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
           )""",
    )


def applied(dbname: str) -> dict[str, str]:
    out = psql(
        dbname,
        "-A", "-t", "-F", "|",
        "-c", "SELECT filename, checksum FROM schema_migrations ORDER BY filename",
        capture=True,
    )
    result: dict[str, str] = {}
    for line in out.splitlines():
        if line.strip():
            name, checksum = line.split("|", 1)
            result[name] = checksum
    return result


def run(dbname: str, directory: Path) -> list[str]:
    files = sorted(p for p in directory.glob("*.sql"))
    for p in files:
        if not FILENAME_RE.match(p.name):
            raise MigrationError(f"마이그레이션 파일명 규칙(NNNN_name.sql) 위반: {p.name}")
    ensure_history_table(dbname)
    done = applied(dbname)

    # 적용 이력에는 있는데 디스크에 없는 파일, 내용이 바뀐 파일을 먼저 점검한다.
    on_disk = {p.name for p in files}
    for name in done:
        if name not in on_disk:
            raise MigrationError(f"적용된 마이그레이션 파일이 디렉터리에 없습니다: {name}")
    for p in files:
        if p.name in done and done[p.name] != sha256(p):
            raise MigrationError(f"적용된 마이그레이션이 수정되었습니다(체크섬 불일치): {p.name}")

    newly: list[str] = []
    for p in files:
        if p.name in done:
            continue
        checksum = sha256(p)
        # -1: 파일 전체를 단일 트랜잭션으로 실행하고, 이력 기록도 같은 트랜잭션에 포함한다.
        psql(
            dbname,
            "-1",
            "-f", str(p),
            "-c",
            f"INSERT INTO schema_migrations (filename, checksum) VALUES ('{p.name}', '{checksum}')",
        )
        newly.append(p.name)
        print(f"적용: {p.name}")
    if not newly:
        print("적용할 새 마이그레이션이 없습니다.")
    return newly


def main() -> int:
    default_dir = Path(__file__).resolve().parent.parent / "migrations"
    ap = argparse.ArgumentParser(description="SQL 마이그레이션 실행기")
    ap.add_argument("--dbname", required=True, help="대상 데이터베이스 이름 (미리 생성되어 있어야 함)")
    ap.add_argument("--dir", type=Path, default=default_dir, help="마이그레이션 디렉터리")
    args = ap.parse_args()
    try:
        run(args.dbname, args.dir)
    except MigrationError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
