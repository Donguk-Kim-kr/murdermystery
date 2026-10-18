"""공통 진행단계를 정리한다: 최신 내용만 남기고 나머지 버전을 모두 지운 뒤 v1 로 다시 만든다.

먼저 기본 진행단계를 최신으로 등록(바뀐 것만 새 버전)한 다음 정리하므로, 끝나면 코드의 최신 스크립트가 v1 로 남는다.
이미 놓은 카드는 새 v1 로 옮겨져 그대로 이어진다. 여러 번 실행해도 안전하다.
접속 정보는 libpq 표준 환경변수(PGHOST, PGUSER, PGPASSWORD, PGDATABASE)를 따른다.
  docker compose exec app python backend/scripts/reset_common_phases.py
"""
import os
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.common_phases import register, reset_to_v1  # noqa: E402


def main() -> None:
    with psycopg.connect(dbname=os.environ.get("PGDATABASE", "murder_mystery")) as conn:
        done = register(conn) + reset_to_v1(conn)
    print("\n".join(done) if done else "바뀐 것이 없습니다(이미 모두 v1 하나씩입니다).")


if __name__ == "__main__":
    main()
