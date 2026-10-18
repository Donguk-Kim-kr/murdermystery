"""시연용 샘플 작품 「동짓날 마을회관」을 만든다(확정·공개까지). 이미 있으면 아무것도 하지 않는다.

기본 진행단계가 등록되어 있어야 하므로 먼저 등록하고(여러 번 해도 안전), 만든다. 접속 정보는 libpq 표준 환경변수를 따른다.
  docker compose exec app python backend/scripts/seed_demo_work.py
컨테이너를 켤 때 docker_start.py 가 자동으로 부른다.
"""
import os
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.common_phases import register  # noqa: E402
from app.demo_work import seed  # noqa: E402


def main() -> None:
    with psycopg.connect(dbname=os.environ.get("PGDATABASE", "murder_mystery"), autocommit=True) as conn:
        register(conn)
    os.environ.setdefault("MM_DATABASE_URL", f"dbname={os.environ.get('PGDATABASE', 'murder_mystery')}")
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        print(f"샘플 작품: {seed(client)}")


if __name__ == "__main__":
    main()
