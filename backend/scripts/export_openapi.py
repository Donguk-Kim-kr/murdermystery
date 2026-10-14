"""FastAPI 앱의 OpenAPI 명세를 표준 출력으로 내보낸다 (서버·DB 없이 실행 가능).

프론트엔드에서 `npm run gen:api` 가 이 스크립트를 호출해 API 타입을 생성한다.
backend 의존성이 설치된 Python 으로 실행해야 한다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

json.dump(app.openapi(), sys.stdout, ensure_ascii=False, indent=2)
