-- 0003_phase_gimmick_library.sql
-- 영역: 재사용 라이브러리 (진행단계 / 기믹)
-- 기준: db/spec/schema_spec.xlsx (시트 '진행단계', '기믹')
--
-- "계정_번호"가 NULL이면 공통(시스템 제공) 항목, 값이 있으면 해당 제작자의 항목이다.
-- 라이브러리 항목은 작품에 적용될 때 0004의 "진행구성"/"기믹적용"이 참조하며,
-- 게임 실행 시에는 이 테이블이 아니라 "버전"."시나리오" 스냅샷을 기준으로 한다.
-- JSONB 컬럼("규칙", "조건", "결과")의 내부 구조는 확정되지 않았으므로 형식 CHECK를 두지 않는다.

CREATE TABLE "진행단계" (
    "번호"      INTEGER  GENERATED ALWAYS AS IDENTITY,
    "이름"      TEXT     NOT NULL,
    "규칙"      JSONB    NOT NULL,
    "설명"      TEXT     NOT NULL,
    "계정_번호" INTEGER,
    CONSTRAINT "pk_진행단계"      PRIMARY KEY ("번호"),
    CONSTRAINT "fk_진행단계_계정" FOREIGN KEY ("계정_번호")
        REFERENCES "계정" ("번호") ON DELETE RESTRICT
);

CREATE INDEX "ix_진행단계_계정" ON "진행단계" ("계정_번호");

CREATE TABLE "기믹" (
    "번호"      INTEGER  GENERATED ALWAYS AS IDENTITY,
    "계정_번호" INTEGER,
    "이름"      TEXT     NOT NULL,
    "설명"      TEXT,
    "조건"      JSONB    NOT NULL,
    "결과"      JSONB    NOT NULL,
    CONSTRAINT "pk_기믹"      PRIMARY KEY ("번호"),
    CONSTRAINT "fk_기믹_계정" FOREIGN KEY ("계정_번호")
        REFERENCES "계정" ("번호") ON DELETE RESTRICT
);

CREATE INDEX "ix_기믹_계정" ON "기믹" ("계정_번호");
