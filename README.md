# 머더미스터리 플랫폼

시나리오 제작 툴(PC)과 플레이(PC·모바일)를 제공하는 웹 플랫폼. 진행 상황은 `docs/HANDOFF_2026-10-14.md` 참고.

## 구성

| 디렉터리 | 내용 |
|---|---|
| `db/` | PostgreSQL 마이그레이션, 실행기, DB 테스트 |
| `backend/` | FastAPI + psycopg 3 (SQL 직접 작성) |
| `frontend/` | React + Vite + TypeScript |
| `docs/` | 스키마·규칙 문서 |

## 실행

접속 정보는 libpq 표준 환경변수를 따른다.

```bash
export PGHOST=127.0.0.1 PGPORT=5432 PGUSER=postgres PGPASSWORD=...

# 1) DB
createdb murder_mystery
python3 db/scripts/migrate.py --dbname murder_mystery

# 2) 백엔드 (http://127.0.0.1:8000, 명세: /docs)
cd backend && pip install -r requirements.txt
uvicorn app.main:app --port 8000          # DB 는 MM_DATABASE_URL 로 바꿀 수 있다 (기본: dbname=murder_mystery)

# 3) 프론트엔드 (http://localhost:5173, /api 는 8000 으로 프록시)
cd frontend && npm install
npm run dev
```

## 테스트

```bash
cd db/tests && python3 -m unittest discover -s . -p 'test_*.py'   # 약 100초, CREATEDB 권한 필요
cd backend && pip install -r requirements-dev.txt && pytest       # 임시 DB 를 만들어 사용
cd frontend && npm test && npm run typecheck
```

## API 타입 생성

백엔드 API 가 바뀌면 프론트 타입을 다시 생성해 `src/api/schema.d.ts` 를 함께 커밋한다.
backend 의존성이 설치된 Python 이 PATH 에 있어야 한다.

```bash
cd frontend && npm run gen:api
```

`typescript` 는 5.x 로 고정한다. `openapi-typescript` 가 TypeScript 5 의 컴파일러 API 를 쓰므로 7.x 에서는 동작하지 않는다.
