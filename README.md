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

## 방 시험하기 (확정 기능이 생기기 전)

방은 확정된 버전이 있는 작품으로만 만들 수 있고, 확정 기능이 아직 없다. 개발 중에는 작품의 확정 버전을 SQL 로 넣어서 시험한다.

```sql
INSERT INTO "버전" ("작품_번호", "버전", "시나리오") VALUES (<작품 번호>, '1.0', '{}'::jsonb);
```

대기실의 입장자 목록은 서버 메모리에 있으므로 백엔드는 **한 프로세스**로 실행해야 한다 (`uvicorn` 에 `--workers` 를 쓰지 않는다).

## 글꼴

앱 화면의 글꼴은 [Pretendard](https://github.com/orioncactus/pretendard)(SIL OFL 1.1)를 `npm` 패키지로 포함해서 기기마다 같게 보인다. 라이선스 문서는 `/licenses/Pretendard-OFL-1.1.txt` 로 함께 배포된다.
제작자가 시나리오(플레이 화면)에서 쓸 글꼴을 직접 올리는 기능은 아직 없다.

## 권한

`계정.권한`은 `사용자`(기본값) < `관리자` < `운영자` 3단계이다. 가입 API 로는 올릴 수 없고, 운영자·관리자 지정 기능은 아직 없다.
첫 운영자는 DB 에서 직접 지정한다.

```sql
UPDATE "계정" SET "권한" = '운영자' WHERE "아이디" = '내 아이디';
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
