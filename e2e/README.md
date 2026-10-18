# 브라우저 시험 (Playwright)

실제 브라우저 3개(PC 2개, 모바일 폭 1개)로 서버를 쓰는 시험이다. 서버(`frontend/dist` 를 서빙하는 백엔드)와 DB 가 떠 있어야 한다.

```bash
# 1. 프런트 빌드, 마이그레이션 적용, 공통 진행단계 등록
cd frontend && npm run build && cd ..
python3 backend/scripts/register_common_phases.py     # PGHOST 등 환경변수 필요
# 2. 서버를 띄운다(예: MM_STATIC_DIR=frontend/dist uvicorn app.main:app --port 8000, backend 폴더에서)
# 3. 시험 실행 (스크린샷을 저장할 폴더를 인자로)
PLAYWRIGHT_MODULE=/경로/playwright/index.mjs node e2e/full_flow.mjs /tmp/shots
```

- `first_flow.mjs`: 프롤로그 → 캐릭터 선택(같은 인물 동시 확인) → 프로필 숙지(자기 서사만 보임, 새로고침 복원)
- `full_flow.mjs`: 공통 진행단계 12개를 끝까지(조사, 토론의 보여 주기·양도, 비공개 투표, 조건에 따른 엔딩, 전체 공개)
- `flow_drag.mjs`: 흐름 화면에서 페이즈 카드를 끌기 시작하는 순간 다른 카드가 밀리지 않는지, 실제로 옮기면 순서가 바뀌는지
- 환경변수: `BASE_URL`(기본 `http://localhost:8000`), `CHROMIUM_PATH`, `PLAYWRIGHT_MODULE`
- 시험은 새 계정과 작품을 만들어 쓰므로 개발 DB 에 시험 데이터가 남는다.
