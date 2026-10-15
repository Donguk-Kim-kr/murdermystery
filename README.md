# 머더미스터리 플랫폼

시나리오 제작 툴(PC)과 플레이(PC·모바일)를 제공하는 웹 플랫폼. 진행 상황은 `docs/HANDOFF_2026-10-14.md` 참고.

## 구성

| 디렉터리 | 내용 |
|---|---|
| `db/` | PostgreSQL 마이그레이션, 실행기, DB 테스트 |
| `backend/` | FastAPI + psycopg 3 (SQL 직접 작성) |
| `frontend/` | React + Vite + TypeScript |
| `docs/` | 스키마·규칙 문서 |

## Docker 로 한 번에 실행 (Windows 포함)

Docker Desktop 이 실행 중이어야 한다. 프로젝트 폴더에서 PowerShell 또는 터미널로:

```
docker compose up --build
```

처음에는 이미지를 만드느라 몇 분 걸린다. `데이터베이스 ... 마이그레이션 적용 ...  Uvicorn running` 이 보이면 브라우저에서 **http://localhost:8000** 을 연다. (화면과 API 가 같은 주소에서 나온다. API 명세는 `/docs`.)

| 하려는 일 | 명령 |
|---|---|
| 끄기 | `Ctrl+C`, 또는 다른 터미널에서 `docker compose down` (데이터는 남는다) |
| 다시 켜기 | `docker compose up` |
| 코드를 새로 받은 뒤(`git pull`) | `docker compose up --build` |
| 데이터까지 모두 지우고 처음부터 | `docker compose down -v` |
| 내 계정을 운영자로 만들기 | `docker compose exec db psql -U postgres -d murder_mystery -c "UPDATE 계정 SET 권한 = '운영자' WHERE 아이디 = '내아이디'"` |

* 내 컴퓨터(`127.0.0.1`)에서만 열린다. 8000 번 포트가 이미 쓰이고 있으면 `docker-compose.yml` 의 `127.0.0.1:8000:8000` 앞 숫자를 바꾼다.
* 비밀번호(`devpassword`)는 개발용이다. 이 설정 그대로 인터넷에 공개하지 않는다.
* 이 방식은 서버 컨테이너가 하나(프로세스 하나)여야 대기실이 동작한다. 컨테이너 수를 늘리지 않는다.
* 개발자용 실행(아래)과 같은 PostgreSQL 이 이미 설치되어 있어도 충돌하지 않는다(DB 포트를 바깥에 열지 않는다).

## 실행 (개발자용: 백엔드·프론트엔드를 따로)

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
