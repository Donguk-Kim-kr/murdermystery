# 머더미스터리 플랫폼

시나리오 제작 툴(PC)과 플레이(PC·모바일)를 제공하는 웹 플랫폼. 진행 상황은 `docs/HANDOFF_2026-10-14.md` 참고.

## 빠른 시작 (시연)

도커 빌드와 실행:

```
docker compose up --build
```

AI 를 방에 입장시키기(다른 터미널에서, 입장코드를 바꿔 넣는다):

```
docker compose exec app python backend/scripts/ai_players.py --code 1234 --count 4
```

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
| 시연용 샘플 작품 | 켤 때 자동으로 만들어져 "게임 목록"에 「동짓날 마을회관」(4인)이 나온다. 수동 실행: `docker compose exec app python backend/scripts/seed_demo_work.py` |
| 내 계정을 운영자로 만들기 | `docker compose exec db psql -U postgres -d murder_mystery -c "UPDATE 계정 SET 권한 = '운영자' WHERE 아이디 = '내아이디'"` |

* 내 컴퓨터(`127.0.0.1`)에서만 열린다. 8000 번 포트가 이미 쓰이고 있으면 `docker-compose.yml` 의 `127.0.0.1:8000:8000` 앞 숫자를 바꾼다.
* 비밀번호(`devpassword`)는 개발용이다. 이 설정 그대로 인터넷에 공개하지 않는다.
* 이 방식은 서버 컨테이너가 하나(프로세스 하나)여야 대기실이 동작한다. 컨테이너 수를 늘리지 않는다.
* 개발자용 실행(아래)과 같은 PostgreSQL 이 이미 설치되어 있어도 충돌하지 않는다(DB 포트를 바깥에 열지 않는다).

## AI 플레이어

AI 가 플레이어로 들어와 게임을 한다(`backend/scripts/ai_players.py`). Anthropic API 키가 필요하다.

1. 프로젝트 폴더에 `.env` 파일을 만들고 한 줄을 적는다(이 파일은 저장소에 올라가지 않는다). 모델은 `MM_AI_MODEL=...` 로 바꿀 수 있다.
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```
2. `docker compose up --build` 로 켠다.
3. 브라우저에서 방을 만든다. AI 가 4명을 다 채우도록 **"방장도 플레이어로 참여"를 끄고**, 대기실에서 관전 방식을 **GM** 으로 바꾼다. 입장코드를 확인한다.
4. 다른 터미널에서 AI 를 입장시킨다(코드를 바꿔 넣는다).
   ```
   docker compose exec app python backend/scripts/ai_players.py --code 1234 --count 4
   ```
5. 방장이 게임을 시작하고 단계를 넘긴다. GM 관전이면 AI 들의 대화와 개인 정보를 모두 볼 수 있다. 끝나면 `Ctrl+C`.

키 없이 흐름만 보려면 `--brain simple` 을 붙인다(말투는 살지 않는다). `--verbose` 를 붙이면 AI 에게 준 글이 출력된다.

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

## 작업공간과 방 시험하기

작품 화면의 탭(개요 / 장소·단서 / 사건 / 관계·자료 / 진행 / 결말 / 확정)은 순서와 무관하게 채울 수 있다. 진행단계·기믹은 상단 "라이브러리"에서 만든다. **확정** 탭에서 확정하면 방을 만들 수 있다(방은 확정된 버전이 있는 작품으로만 만들 수 있다). 시험용으로 빈 스냅샷을 SQL 로 넣을 수도 있다.

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
