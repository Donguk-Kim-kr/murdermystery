"""PostgreSQL 연결 풀 (psycopg 3, SQL 직접 작성)."""
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import Settings


def create_pool(settings: Settings) -> ConnectionPool:
    # open=False: 열기는 앱 시작(lifespan)에서 한다. 접속 실패는 start 시 즉시 드러나게 wait() 한다.
    return ConnectionPool(
        settings.database_url,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
        kwargs={"row_factory": dict_row},
        open=False,
    )


def get_conn(request: Request) -> Iterator[Connection]:
    """요청마다 풀에서 연결을 빌린다. 예외 없이 끝나면 커밋, 예외가 나면 롤백된다."""
    with request.app.state.pool.connection() as conn:
        yield conn


# scope="function": 엔드포인트가 끝나면 응답을 보내기 전에 커밋/롤백한다.
# (기본값은 응답 전송 후 종료라서, 클라이언트가 커밋 전에 다음 요청을 보낼 수 있다.)
Conn = Annotated[Connection, Depends(get_conn, scope="function")]
