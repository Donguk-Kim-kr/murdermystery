-- 0008_publish_right_and_testers.sql
-- 영역: 작품 공개 권한 / 테스터
-- 명세서 변경(사용자 결정, 2026-10-14):
--   1) "작품"."공개권한": 비공개 상태에서 '누가 다시 공개할 수 있는가'를 나타낸다.
--      제작자 / 관리자 / 운영자 (docs/DB_RULES.md B35). 새 작품은 '제작자'.
--   2) "작품테스터": 제작자(자기 작품)·관리자·운영자가 계정에 주는 작품별 테스트 플레이 권한 (B36).
--      서버 전체 권한이 아니라 작품 단위 관계이다.
-- 이 규칙의 판단(요청자 권한 + 작품 소유자)은 DB 가 할 수 없으므로 백엔드에서 검증한다.

ALTER TABLE "작품" ADD COLUMN "공개권한" TEXT NOT NULL DEFAULT '제작자';

ALTER TABLE "작품"
    ADD CONSTRAINT "ck_작품_공개권한" CHECK ("공개권한" IN ('제작자', '관리자', '운영자'));

CREATE TABLE "작품테스터" (
    "번호"      INTEGER       GENERATED ALWAYS AS IDENTITY,
    "작품_번호" INTEGER       NOT NULL,
    "계정_번호" INTEGER       NOT NULL,
    "부여일시"  TIMESTAMPTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "pk_작품테스터"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_작품테스터_작품_계정" UNIQUE ("작품_번호", "계정_번호"),
    CONSTRAINT "fk_작품테스터_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_작품테스터_계정"      FOREIGN KEY ("계정_번호")
        REFERENCES "계정" ("번호") ON DELETE CASCADE
);

CREATE INDEX "ix_작품테스터_계정" ON "작품테스터" ("계정_번호");
