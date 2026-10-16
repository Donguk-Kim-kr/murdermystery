-- 엔딩분기에 이름 칸을 추가한다 (기록 화면 등에서 "엔딩: ○○"으로 보여 주기 위해. 사용자 결정 2026-10-16).
--
-- 컬럼 순서를 번호, 작품_번호, 순서, 이름, 조건, 내용으로 맞추려고 테이블을 다시 만든다(PostgreSQL 은 컬럼 사이에 끼워 넣을 수 없다).
-- 엔딩분기를 가리키는 외래키는 없다(엔딩.엔딩분기_순서는 확정 스냅샷 안의 번호이다).
-- 이름은 다른 콘텐츠(장소, 단서 …)처럼 필수이다. 이미 있는 행은 "엔딩 <순서>"로 채운다.

DO $$
DECLARE seq text;
BEGIN
    seq := pg_get_serial_sequence('"엔딩분기"', '번호');
    ALTER TABLE "엔딩분기" RENAME TO "엔딩분기_구";
    EXECUTE format('ALTER SEQUENCE %s RENAME TO %I', seq, '엔딩분기_구_번호_seq');
END $$;
ALTER TABLE "엔딩분기_구" RENAME CONSTRAINT "pk_엔딩분기"           TO "pk_엔딩분기_구";
ALTER TABLE "엔딩분기_구" RENAME CONSTRAINT "uq_엔딩분기_작품_순서" TO "uq_엔딩분기_구_작품_순서";
ALTER TABLE "엔딩분기_구" RENAME CONSTRAINT "fk_엔딩분기_작품"      TO "fk_엔딩분기_구_작품";
ALTER TABLE "엔딩분기_구" RENAME CONSTRAINT "ck_엔딩분기_순서"      TO "ck_엔딩분기_구_순서";

CREATE TABLE "엔딩분기" (
    "번호"      INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호" INTEGER  NOT NULL,
    "순서"      INTEGER  NOT NULL,
    "이름"      TEXT     NOT NULL,
    "조건"      JSONB    NOT NULL,
    "내용"      TEXT     NOT NULL,
    CONSTRAINT "pk_엔딩분기"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_엔딩분기_작품_순서" UNIQUE ("작품_번호", "순서"),
    CONSTRAINT "fk_엔딩분기_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "ck_엔딩분기_순서"      CHECK ("순서" >= 1)
);

INSERT INTO "엔딩분기" ("번호", "작품_번호", "순서", "이름", "조건", "내용")
OVERRIDING SYSTEM VALUE
SELECT "번호", "작품_번호", "순서", '엔딩 ' || "순서", "조건", "내용" FROM "엔딩분기_구";

SELECT setval(pg_get_serial_sequence('"엔딩분기"', '번호'), COALESCE((SELECT max("번호") FROM "엔딩분기"), 0) + 1, false);

DROP TABLE "엔딩분기_구";
