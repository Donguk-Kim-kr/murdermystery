"""컨테이너 시작 스크립트: DB 가 준비되길 기다리고, 마이그레이션을 적용한 뒤 서버를 실행한다.

* 접속 정보는 libpq 표준 환경변수(PGHOST, PGUSER, PGPASSWORD, PGDATABASE)를 따른다.
* 서버는 **한 프로세스**로만 실행한다. 대기실의 입장자가 서버 메모리에 있기 때문이다 (docs/DB_RULES.md B38).
* 경로는 이 파일 위치를 기준으로 계산하므로 컨테이너 밖에서도 같은 방식으로 시험할 수 있다.
"""
import os
import sys
import time
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "db" / "scripts"))
import migrate  # noqa: E402  (db/scripts/migrate.py)

DBNAME = os.environ.get("PGDATABASE", "murder_mystery")
WAIT_SECONDS = 60


def wait_for_database() -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while True:
        try:
            with psycopg.connect(dbname=DBNAME, connect_timeout=3):
                return
        except psycopg.OperationalError as exc:
            if time.monotonic() > deadline:
                sys.exit(f"데이터베이스에 연결하지 못했습니다 ({WAIT_SECONDS}초 대기): {exc}")
            print("데이터베이스를 기다리는 중...", flush=True)
            time.sleep(2)


def main() -> None:
    wait_for_database()
    applied = migrate.run(DBNAME, ROOT / "db" / "migrations")
    print(f"마이그레이션 적용 {len(applied)}건", flush=True)
    port = os.environ.get("PORT", "8000")
    os.chdir(ROOT / "backend")
    os.execvp(sys.executable, [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", port])


if __name__ == "__main__":
    main()
