-- 사용법: psql -d murder_mystery -v ON_ERROR_STOP=1 -v me=내아이디 -f db/scripts/reset_except_me.sql
-- 내 계정(과 로그인 상태)과 마이그레이션 이력만 남기고 모두 지운다. 마이그레이션 0015 가 넣은 공통 진행단계도 지운다.
BEGIN;

-- 아이디가 없으면 여기서 오류로 멈추고(ON_ERROR_STOP) 아무것도 지우지 않는다.
SELECT "번호" AS me_id FROM "계정" WHERE "아이디" = :'me' \gset

-- 1) 작품·진행·방·참여·진행단계·기믹 등 모든 데이터 테이블 비우기 (계정, 로그인세션, 이력 제외)
DO $$
DECLARE names text;
BEGIN
  SELECT string_agg(format('%I', tablename), ', ') INTO names
  FROM pg_tables
  WHERE schemaname = 'public' AND tablename NOT IN ('계정', '로그인세션', 'schema_migrations');
  EXECUTE 'TRUNCATE ' || names || ' RESTART IDENTITY';
END $$;

-- 2) 다른 계정 삭제
DELETE FROM "로그인세션" WHERE "계정_번호" <> :me_id;
DELETE FROM "계정"       WHERE "번호"      <> :me_id;

COMMIT;
