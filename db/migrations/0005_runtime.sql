-- 0005_runtime.sql
-- 영역: 게임 실행 테이블 (방 / 진행 / 참여 / 기믹실행 / 투표결과 / 엔딩 / 획득)
-- 기준: db/spec/schema_spec.xlsx (시트 '방' ~ '획득')
--
-- 설계 원칙
--  * 게임은 "진행"이 가리키는 확정 버전의 "버전"."시나리오"(JSONB 스냅샷)를 기준으로 동작한다.
--  * 아래 테이블의 "*_순서" 컬럼(인물_순서, 단서_순서, 증언_순서, 조합_순서, 진행순서_순서,
--    투표_순서, 기믹적용_순서, 엔딩분기_순서, 후일담_순서)은 스냅샷 안의 순서 번호이다.
--    제작용 콘텐츠 테이블(0004)을 FK 로 참조하지 않으므로, 제작용 콘텐츠가 이후 수정·삭제되어도
--    이미 생성된 게임과 기록은 영향을 받지 않는다.
--    스냅샷 안에 해당 순서가 존재하는지는 DB 로 검증할 수 없으며 백엔드에서 검증한다.
--  * 기록 보존을 위해 작품·버전·계정·방에 대한 FK 는 삭제 불가(RESTRICT)이다.
--    "진행"에 종속된 기록(참여, 기믹실행, 엔딩, 획득, 투표결과)은 "진행" 삭제 시 함께 삭제(CASCADE)된다.
--  * JSONB 컬럼("기믹실행"."결과")의 내부 구조는 확정되지 않았으므로 형식 CHECK를 두지 않는다.

CREATE TABLE "방" (
    "번호"          INTEGER      GENERATED ALWAYS AS IDENTITY,
    "계정_번호"     INTEGER      NOT NULL,
    "입장코드"      TEXT         NOT NULL,
    "상태"          TEXT         NOT NULL DEFAULT '대기',
    "생성일시"      TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "상태변경일시"  TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "종료일시"      TIMESTAMPTZ,
    CONSTRAINT "pk_방"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_방_입장코드"  UNIQUE ("입장코드"),
    CONSTRAINT "fk_방_계정"      FOREIGN KEY ("계정_번호")
        REFERENCES "계정" ("번호") ON DELETE RESTRICT,
    CONSTRAINT "ck_방_상태"      CHECK ("상태" IN ('대기', '진행', '종료'))
);

CREATE INDEX "ix_방_계정" ON "방" ("계정_번호");

CREATE TABLE "진행" (
    "번호"          INTEGER      GENERATED ALWAYS AS IDENTITY,
    "방_번호"       INTEGER      NOT NULL,
    "작품_번호"     INTEGER      NOT NULL,
    "버전_버전"     TEXT         NOT NULL,
    "진행순서_순서" INTEGER,
    "시작일시"      TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "종료일시"      TIMESTAMPTZ,
    "상태"          TEXT         NOT NULL DEFAULT '진행',
    CONSTRAINT "pk_진행"        PRIMARY KEY ("번호"),
    CONSTRAINT "fk_진행_방"     FOREIGN KEY ("방_번호")
        REFERENCES "방" ("번호") ON DELETE RESTRICT,
    CONSTRAINT "fk_진행_작품"   FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE RESTRICT,
    CONSTRAINT "fk_진행_버전"   FOREIGN KEY ("작품_번호", "버전_버전")
        REFERENCES "버전" ("작품_번호", "버전") ON DELETE RESTRICT,
    CONSTRAINT "ck_진행_상태"   CHECK ("상태" IN ('진행', '종료'))
);

CREATE INDEX "ix_진행_방"   ON "진행" ("방_번호");
CREATE INDEX "ix_진행_버전" ON "진행" ("작품_번호", "버전_버전");

CREATE TABLE "참여" (
    "번호"      INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호" INTEGER  NOT NULL,
    "진행_번호" INTEGER  NOT NULL,
    "계정_번호" INTEGER  NOT NULL,
    "인물_순서" INTEGER,
    "후기"      TEXT,
    "비공개"    BOOLEAN  NOT NULL DEFAULT FALSE,
    CONSTRAINT "pk_참여"              PRIMARY KEY ("번호"),
    CONSTRAINT "uq_참여_진행_계정"    UNIQUE ("진행_번호", "계정_번호"),
    CONSTRAINT "uq_참여_진행_인물"    UNIQUE ("진행_번호", "인물_순서"),
    CONSTRAINT "fk_참여_작품"         FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE RESTRICT,
    CONSTRAINT "fk_참여_진행"         FOREIGN KEY ("진행_번호")
        REFERENCES "진행" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_참여_계정"         FOREIGN KEY ("계정_번호")
        REFERENCES "계정" ("번호") ON DELETE RESTRICT
);

CREATE INDEX "ix_참여_작품" ON "참여" ("작품_번호");
CREATE INDEX "ix_참여_계정" ON "참여" ("계정_번호");

CREATE TABLE "기믹실행" (
    "번호"            INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호"       INTEGER  NOT NULL,
    "진행_번호"       INTEGER  NOT NULL,
    "기믹적용_순서"   INTEGER  NOT NULL,
    "실행여부"        BOOLEAN  NOT NULL DEFAULT FALSE,
    "결과"            JSONB,
    CONSTRAINT "pk_기믹실행"            PRIMARY KEY ("번호"),
    -- 명세서는 이 제약을 '실행여부' 행에 적었으나 컬럼 목록이 (진행_번호, 기믹적용_순서)이므로
    -- 해당 두 컬럼의 복합 UNIQUE 로 해석했다. (docs/SCHEMA_REPORT.md 확인 요청 항목)
    CONSTRAINT "uq_기믹실행_진행_적용"  UNIQUE ("진행_번호", "기믹적용_순서"),
    CONSTRAINT "fk_기믹실행_작품"       FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE RESTRICT,
    CONSTRAINT "fk_기믹실행_진행"       FOREIGN KEY ("진행_번호")
        REFERENCES "진행" ("번호") ON DELETE CASCADE
);

CREATE INDEX "ix_기믹실행_작품" ON "기믹실행" ("작품_번호");

CREATE TABLE "투표결과" (
    "번호"      INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호" INTEGER  NOT NULL,
    "투표_순서" INTEGER  NOT NULL,
    "참여_번호" INTEGER  NOT NULL,
    "선택"      TEXT     NOT NULL,
    CONSTRAINT "pk_투표결과"             PRIMARY KEY ("번호"),
    CONSTRAINT "uq_투표결과_투표_참여"   UNIQUE ("작품_번호", "투표_순서", "참여_번호"),
    CONSTRAINT "fk_투표결과_작품"        FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE RESTRICT,
    CONSTRAINT "fk_투표결과_참여"        FOREIGN KEY ("참여_번호")
        REFERENCES "참여" ("번호") ON DELETE CASCADE
);

CREATE INDEX "ix_투표결과_참여" ON "투표결과" ("참여_번호");

CREATE TABLE "엔딩" (
    "번호"           INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호"      INTEGER  NOT NULL,
    "진행_번호"      INTEGER  NOT NULL,
    "순서"           INTEGER  NOT NULL,
    "엔딩분기_순서"  INTEGER,
    "후일담_순서"    INTEGER,
    CONSTRAINT "pk_엔딩"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_엔딩_진행_순서" UNIQUE ("진행_번호", "순서"),
    CONSTRAINT "fk_엔딩_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE RESTRICT,
    CONSTRAINT "fk_엔딩_진행"      FOREIGN KEY ("진행_번호")
        REFERENCES "진행" ("번호") ON DELETE CASCADE,
    CONSTRAINT "ck_엔딩_순서"      CHECK ("순서" >= 1),
    -- 한 행은 엔딩분기 또는 후일담 중 정확히 하나만 가리킨다. (확정: 정확히 1개)
    CONSTRAINT "ck_엔딩_하나"      CHECK (num_nonnulls("엔딩분기_순서", "후일담_순서") = 1)
);

CREATE INDEX "ix_엔딩_작품" ON "엔딩" ("작품_번호");

CREATE TABLE "획득" (
    "번호"           INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호"      INTEGER  NOT NULL,
    "진행_번호"      INTEGER  NOT NULL,
    "참여_번호"      INTEGER  NOT NULL,
    "단서_순서"      INTEGER,
    "증언_순서"      INTEGER,
    "조합_순서"      INTEGER,
    "진행순서_순서"  INTEGER  NOT NULL,
    "획득방법"       TEXT     NOT NULL,
    "보유여부"       BOOLEAN  NOT NULL DEFAULT TRUE,
    CONSTRAINT "pk_획득"        PRIMARY KEY ("번호"),
    CONSTRAINT "fk_획득_작품"   FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE RESTRICT,
    CONSTRAINT "fk_획득_진행"   FOREIGN KEY ("진행_번호")
        REFERENCES "진행" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_획득_참여"   FOREIGN KEY ("참여_번호")
        REFERENCES "참여" ("번호") ON DELETE CASCADE,
    CONSTRAINT "ck_획득_하나"   CHECK (num_nonnulls("단서_순서", "증언_순서", "조합_순서") = 1)
);

CREATE INDEX "ix_획득_작품" ON "획득" ("작품_번호");
CREATE INDEX "ix_획득_진행" ON "획득" ("진행_번호");
CREATE INDEX "ix_획득_참여" ON "획득" ("참여_번호");
