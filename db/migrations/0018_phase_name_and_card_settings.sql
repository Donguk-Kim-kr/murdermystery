-- 게임 흐름 설계 보강 (사용자 결정 2026-10-16/17).
--
--  * 진행순서(페이즈 칸)에 이름을 추가한다. 플레이어에게 보이는 페이즈 이름이며 비워 둘 수 있다.
--  * 진행구성(칸에 놓인 진행단계 카드)과 기믹적용(칸에 붙은 기믹)에 설정(JSONB)을 추가한다.
--    카드를 놓을 때 제작자가 정의의 기본값을 덮어쓰는 세부 설정(조사 횟수, 탭을 남길지 등)이며, 비어 있으면 정의의 기본값을 쓴다.
--    JSONB 내부 구조는 엔진 설계 때 정한다(임의로 정하지 않는다).
--
-- 페이즈를 끼워 넣거나 옮길 때는 칸(순서)을 그대로 두고 칸에 매달린 내용(진행구성·기믹적용·투표·미디어와 진행시간·이름)을
-- 서버가 옮긴다. 그래서 외래키 구조는 바꾸지 않는다.
--
-- 진행순서는 컬럼 순서(번호, 작품_번호, 순서, 이름, 진행시간)를 맞추려고 테이블을 다시 만든다. 이를 가리키는 외래키 4개는 풀었다가 다시 건다.

ALTER TABLE "진행구성"  DROP CONSTRAINT "fk_진행구성_진행순서";
ALTER TABLE "기믹적용"  DROP CONSTRAINT "fk_기믹적용_진행순서";
ALTER TABLE "투표"      DROP CONSTRAINT "fk_투표_진행순서";
ALTER TABLE "미디어"    DROP CONSTRAINT "fk_미디어_진행순서";

DO $$
DECLARE seq text;
BEGIN
    seq := pg_get_serial_sequence('"진행순서"', '번호');
    ALTER TABLE "진행순서" RENAME TO "진행순서_구";
    EXECUTE format('ALTER SEQUENCE %s RENAME TO %I', seq, '진행순서_구_번호_seq');
END $$;
ALTER TABLE "진행순서_구" RENAME CONSTRAINT "pk_진행순서"           TO "pk_진행순서_구";
ALTER TABLE "진행순서_구" RENAME CONSTRAINT "uq_진행순서_작품_순서" TO "uq_진행순서_구_작품_순서";
ALTER TABLE "진행순서_구" RENAME CONSTRAINT "fk_진행순서_작품"      TO "fk_진행순서_구_작품";
ALTER TABLE "진행순서_구" RENAME CONSTRAINT "ck_진행순서_순서"      TO "ck_진행순서_구_순서";
ALTER TABLE "진행순서_구" RENAME CONSTRAINT "ck_진행순서_진행시간"  TO "ck_진행순서_구_진행시간";

CREATE TABLE "진행순서" (
    "번호"      INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호" INTEGER  NOT NULL,
    "순서"      INTEGER  NOT NULL,
    "이름"      TEXT,
    "진행시간"  INTEGER  NOT NULL DEFAULT 30,
    CONSTRAINT "pk_진행순서"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_진행순서_작품_순서" UNIQUE ("작품_번호", "순서"),
    CONSTRAINT "fk_진행순서_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "ck_진행순서_순서"      CHECK ("순서" >= 1),
    CONSTRAINT "ck_진행순서_진행시간"  CHECK ("진행시간" >= 0)
);

INSERT INTO "진행순서" ("번호", "작품_번호", "순서", "진행시간")
OVERRIDING SYSTEM VALUE
SELECT "번호", "작품_번호", "순서", "진행시간" FROM "진행순서_구";

SELECT setval(pg_get_serial_sequence('"진행순서"', '번호'), COALESCE((SELECT max("번호") FROM "진행순서"), 0) + 1, false);

DROP TABLE "진행순서_구";

ALTER TABLE "진행구성" ADD CONSTRAINT "fk_진행구성_진행순서" FOREIGN KEY ("작품_번호", "진행순서_순서")
    REFERENCES "진행순서" ("작품_번호", "순서") ON DELETE CASCADE;
ALTER TABLE "기믹적용" ADD CONSTRAINT "fk_기믹적용_진행순서" FOREIGN KEY ("작품_번호", "진행순서_순서")
    REFERENCES "진행순서" ("작품_번호", "순서") ON DELETE RESTRICT;
ALTER TABLE "투표"     ADD CONSTRAINT "fk_투표_진행순서"     FOREIGN KEY ("작품_번호", "진행순서_순서")
    REFERENCES "진행순서" ("작품_번호", "순서") ON DELETE RESTRICT;
ALTER TABLE "미디어"   ADD CONSTRAINT "fk_미디어_진행순서"   FOREIGN KEY ("작품_번호", "진행순서_순서")
    REFERENCES "진행순서" ("작품_번호", "순서") ON DELETE RESTRICT;

ALTER TABLE "진행구성" ADD COLUMN "설정" JSONB;
ALTER TABLE "기믹적용" ADD COLUMN "설정" JSONB;
