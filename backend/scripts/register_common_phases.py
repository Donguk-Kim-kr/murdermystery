"""기본(공통) 진행단계를 라이브러리에 등록한다. 여러 번 실행해도 안전하다(바뀐 것만 새 버전으로 올린다).

접속 정보는 libpq 표준 환경변수(PGHOST, PGUSER, PGPASSWORD, PGDATABASE)를 따른다.
  docker compose exec backend python backend/scripts/register_common_phases.py
"""
import os
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.common_phases import register  # noqa: E402


def main() -> None:
    with psycopg.connect(dbname=os.environ.get("PGDATABASE", "murder_mystery")) as conn:
        done = register(conn)
    print("\n".join(done) if done else "바뀐 것이 없습니다(이미 모두 등록되어 있습니다).")


if __name__ == "__main__":
    main()
