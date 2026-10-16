-- 참여 테이블에 플레이 기록 칸(평점, 난이도, 후기 공개, 메모)을 추가하고 컬럼 순서를 정리한다.
--
-- 결정(사용자, 2026-10-16):
--   * 평점·난이도: 0~5, 0.5 단위. 남기지 않을 수 있으므로 NULL = "기록 안 함"이다(0 과 다르다).
--     후기만 쓰고 평점이나 난이도를 비워 둘 수도, 반대도 가능하다(서로 묶지 않는다).
--   * 비공개(FALSE=공개) 를 후기공개(TRUE=공개) 로 바꾼다. 값의 뜻이 뒤집히므로 옮길 때 NOT 한다. 기본값은 공개.
--     후기공개는 후기 글에만 적용한다(평점·난이도를 평균에서 뺀다는 뜻이 아니다).
--   * 메모: 본인만 보는 글. 서버가 본인에게만 내려 주어야 한다.
--   * 스포일러 표시는 후기 글 안의 표시 문법으로 하며 DB 에서 다루지 않는다.
--
-- PostgreSQL 은 컬럼 순서를 바꿀 수 없어 테이블을 다시 만든다. 참여를 가리키는 외래키(투표결과, 획득)는 풀었다가 다시 건다.
-- 게임 진행 기능이 아직 없어 옮길 데이터는 없지만, 있어도 그대로 옮긴다.

ALTER TABLE "투표결과" DROP CONSTRAINT "fk_투표결과_참여";
ALTER TABLE "획득"     DROP CONSTRAINT "fk_획득_참여";

-- 새 테이블이 같은 이름을 쓸 수 있도록 옛 테이블의 이름들을 비킨다.
DO $$
DECLARE seq text;
BEGIN
    seq := pg_get_serial_sequence('"참여"', '번호');
    ALTER TABLE "참여" RENAME TO "참여_구";
    EXECUTE format('ALTER SEQUENCE %s RENAME TO %I', seq, '참여_구_번호_seq');
END $$;
ALTER TABLE "참여_구" RENAME CONSTRAINT "pk_참여"           TO "pk_참여_구";
ALTER TABLE "참여_구" RENAME CONSTRAINT "uq_참여_진행_계정" TO "uq_참여_구_진행_계정";
ALTER TABLE "참여_구" RENAME CONSTRAINT "uq_참여_진행_인물" TO "uq_참여_구_진행_인물";
ALTER TABLE "참여_구" RENAME CONSTRAINT "fk_참여_작품"      TO "fk_참여_구_작품";
ALTER TABLE "참여_구" RENAME CONSTRAINT "fk_참여_진행"      TO "fk_참여_구_진행";
ALTER TABLE "참여_구" RENAME CONSTRAINT "fk_참여_계정"      TO "fk_참여_구_계정";
ALTER INDEX "ix_참여_작품" RENAME TO "ix_참여_구_작품";
ALTER INDEX "ix_참여_계정" RENAME TO "ix_참여_구_계정";

CREATE TABLE "참여" (
    "번호"      INTEGER      GENERATED ALWAYS AS IDENTITY,
    "작품_번호" INTEGER      NOT NULL,
    "진행_번호" INTEGER      NOT NULL,
    "계정_번호" INTEGER      NOT NULL,
    "인물_순서" INTEGER,
    "평점"      NUMERIC(2,1),
    "난이도"    NUMERIC(2,1),
    "후기"      TEXT,
    "후기공개"  BOOLEAN      NOT NULL DEFAULT TRUE,
    "메모"      TEXT,
    CONSTRAINT "pk_참여"              PRIMARY KEY ("번호"),
    CONSTRAINT "uq_참여_진행_계정"    UNIQUE ("진행_번호", "계정_번호"),
    CONSTRAINT "uq_참여_진행_인물"    UNIQUE ("진행_번호", "인물_순서"),
    CONSTRAINT "ck_참여_평점"         CHECK ("평점" IS NULL OR ("평점" BETWEEN 0 AND 5 AND "평점" * 2 = trunc("평점" * 2))),
    CONSTRAINT "ck_참여_난이도"       CHECK ("난이도" IS NULL OR ("난이도" BETWEEN 0 AND 5 AND "난이도" * 2 = trunc("난이도" * 2))),
    CONSTRAINT "fk_참여_작품"         FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE RESTRICT,
    CONSTRAINT "fk_참여_진행"         FOREIGN KEY ("진행_번호")
        REFERENCES "진행" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_참여_계정"         FOREIGN KEY ("계정_번호")
        REFERENCES "계정" ("번호") ON DELETE RESTRICT
);

CREATE INDEX "ix_참여_작품" ON "참여" ("작품_번호");
CREATE INDEX "ix_참여_계정" ON "참여" ("계정_번호");

INSERT INTO "참여" ("번호", "작품_번호", "진행_번호", "계정_번호", "인물_순서", "후기", "후기공개")
OVERRIDING SYSTEM VALUE
SELECT "번호", "작품_번호", "진행_번호", "계정_번호", "인물_순서", "후기", NOT "비공개" FROM "참여_구";

-- 새 번호가 옮긴 번호와 겹치지 않게 이어서 센다.
SELECT setval(pg_get_serial_sequence('"참여"', '번호'), COALESCE((SELECT max("번호") FROM "참여"), 0) + 1, false);

DROP TABLE "참여_구";

ALTER TABLE "투표결과" ADD CONSTRAINT "fk_투표결과_참여" FOREIGN KEY ("참여_번호")
    REFERENCES "참여" ("번호") ON DELETE CASCADE;
ALTER TABLE "획득" ADD CONSTRAINT "fk_획득_참여" FOREIGN KEY ("참여_번호")
    REFERENCES "참여" ("번호") ON DELETE CASCADE;
