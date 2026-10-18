-- 인물에 "NPC 순위"와 "선택 화면 소개"를 더한다 (사용자 결정 2026-10-18).
--
--  * NPC순위: 인원이 모자라 일부 인물을 NPC 로 둘 때, 제작자가 정한 순서이다. 1 이 가장 먼저 NPC 가 된다.
--    값이 있는 인물은 "NPC 가 될 수 있는 인물"이다. 값이 없고 NPC 가 아니면 반드시 플레이하는 인물이고,
--    NPC(항상 NPC, 예: 시작부터 죽은 피해자)인 인물에는 순위를 둘 수 없다. 순위는 작품 안에서 겹치지 않는다.
--    작품.최소인원은 (플레이할 수 있는 인물 수 - NPC 가 될 수 있는 인물 수)로 자동 계산한다(애플리케이션).
--  * 선택소개: 캐릭터 선택 단계에서 보여 줄 수 있는 소개. 기존 `소개`는 자기소개 단계의 멘트로 그대로 둔다.
-- 컬럼은 맨 끝에 붙인다(테이블을 가리키는 외래키가 많아 다시 만들지 않는다).

ALTER TABLE "인물" ADD COLUMN "선택소개" TEXT;
ALTER TABLE "인물" ADD COLUMN "NPC순위" INTEGER;
ALTER TABLE "인물" ADD CONSTRAINT "ck_인물_NPC순위" CHECK ("NPC순위" IS NULL OR ("NPC순위" >= 1 AND NOT "NPC"));
CREATE UNIQUE INDEX "uq_인물_NPC순위" ON "인물" ("작품_번호", "NPC순위") WHERE "NPC순위" IS NOT NULL;
