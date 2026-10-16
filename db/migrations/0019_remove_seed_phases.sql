-- 0015 가 시험용으로 넣은 공통 진행단계 11개를 없앤다 (사용자 결정 2026-10-16: 진행단계는 제작자가 직접 만든다).
--
-- 시험용 기본값(계정_번호 NULL, 버전 1, 변경내역 '시험용 기본값')만 대상이다. 운영자가 새 버전을 올렸거나 직접 만든 공통 항목은 건드리지 않는다.
-- 이미 작품의 진행구성이 가리키는 항목은 행을 지우지 못하므로(RESTRICT) 삭제 표시(삭제일시)만 한다.
-- 그 연결은 남아 '삭제된 항목'으로 보이고 다음 확정 때 스냅샷에서 빠진다(docs/DB_RULES.md B39).

UPDATE "진행단계" s
   SET "삭제일시" = CURRENT_TIMESTAMP
 WHERE s."계정_번호" IS NULL AND s."버전" = 1 AND s."변경내역" = '시험용 기본값' AND s."삭제일시" IS NULL
   AND EXISTS (SELECT 1 FROM "진행구성" c WHERE c."진행단계_번호" = s."번호");

DELETE FROM "진행단계" s
 WHERE s."계정_번호" IS NULL AND s."버전" = 1 AND s."변경내역" = '시험용 기본값'
   AND NOT EXISTS (SELECT 1 FROM "진행구성" c WHERE c."진행단계_번호" = s."번호");
