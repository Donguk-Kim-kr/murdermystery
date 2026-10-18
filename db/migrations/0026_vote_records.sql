-- 투표 기록을 실제로 남기기 위해 투표결과를 고친다 (사용자 결정 2026-10-18).
-- 게임의 투표는 제작 콘텐츠의 투표 번호가 아니라 진행단계 카드가 정한 이름(예: "최종 투표")으로 구분된다.
-- 그래서 투표_순서(INTEGER)를 투표이름(TEXT)으로 바꾼다. 컬럼 자리는 그대로다.
-- 지금까지 이 테이블에 쓰는 코드가 없었으므로 비어 있다. 다시 만들어도 잃는 자료가 없다.
-- 이미 적용된 0005 는 고치지 않는다.

DROP TABLE "투표결과";

CREATE TABLE "투표결과" (
    "번호"      INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호" INTEGER  NOT NULL,
    "투표이름"  TEXT     NOT NULL,
    "참여_번호" INTEGER  NOT NULL,
    "선택"      TEXT     NOT NULL,
    CONSTRAINT "pk_투표결과"             PRIMARY KEY ("번호"),
    CONSTRAINT "uq_투표결과_투표_참여"   UNIQUE ("작품_번호", "투표이름", "참여_번호"),
    CONSTRAINT "fk_투표결과_작품"        FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE RESTRICT,
    CONSTRAINT "fk_투표결과_참여"        FOREIGN KEY ("참여_번호")
        REFERENCES "참여" ("번호") ON DELETE CASCADE
);

CREATE INDEX "ix_투표결과_참여" ON "투표결과" ("참여_번호");
