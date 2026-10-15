"""빌드된 프론트엔드(React)를 백엔드가 함께 서비스한다. (Docker 로 한 번에 실행할 때 쓴다)

* `MM_STATIC_DIR` 이 비어 있으면 아무것도 하지 않는다. 개발 중에는 Vite 개발 서버(5173)가 화면을 서비스한다.
* 알 수 없는 경로는 `index.html` 로 돌려준다. (`/works/3` 같은 화면 경로를 새로고침해도 열리게 하려는 것)
* 다만 `/api/...` 와 FastAPI 문서 경로의 오류는 화면이 아니라 JSON 404 로 남겨 둔다.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope

# 화면 대신 오류를 그대로 돌려줄 경로의 앞부분
API_PREFIXES = ("api/", "docs", "redoc", "openapi.json")


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.startswith(API_PREFIXES):
                raise
            return await super().get_response("index.html", scope)


def mount_frontend(app: FastAPI, static_dir: str) -> None:
    directory = Path(static_dir)
    if not (directory / "index.html").is_file():
        raise RuntimeError(f"MM_STATIC_DIR 에 index.html 이 없습니다: {directory}")
    app.mount("/", SPAStaticFiles(directory=directory), name="frontend")
