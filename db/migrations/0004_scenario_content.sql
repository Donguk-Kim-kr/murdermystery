-- 0004_scenario_content.sql
-- 영역: 제작용 콘텐츠 테이블 (작성 중인 시나리오 원본)
-- 기준: db/spec/schema_spec.xlsx (시트 '진행순서' ~ '미디어')
--
-- 공통 규칙
--  * 작품 내부 번호는 ("작품_번호", "순서") 복합 UNIQUE 로 식별하고,
--    다른 테이블은 이 복합 키를 복합 FK 로 참조한다. (작품 간 교차 참조 불가)
--  * nullable 복합 FK 는 PostgreSQL 기본(MATCH SIMPLE)에 따라 순서 컬럼이 NULL 이면 검사하지 않는다.
--  * ON DELETE 정책 (명세서에 없어 설계로 결정한 부분, docs/DB_RULES.md 에 정리)
--      - 작품 삭제 시 모든 제작용 콘텐츠는 함께 삭제(CASCADE)
--      - 부모 없이 의미가 없는 하위 행(진행구성, 관계, 사건설명의 사건, 조합재료의 결과 조합)은 CASCADE
--      - 선택적 연관(NULL 허용) 및 독립적인 제작 콘텐츠 참조는 RESTRICT (참조 중이면 삭제 불가)
--        (작품 삭제 시 CASCADE 와 충돌하지 않는지는 test_isolation_and_triggers.py 의
--         test_deleting_work_without_games_... 가 회귀 테스트로 확인한다.)
--  * 게임 실행 테이블(0005)은 이 테이블들을 FK 로 참조하지 않는다.
--    따라서 이 테이블의 수정·삭제는 이미 생성된 게임과 기록에 영향을 주지 않는다.
--  * JSONB 컬럼("조건", "규칙")의 내부 구조는 확정되지 않았으므로 형식 CHECK를 두지 않는다.

-- ---------------------------------------------------------------------------
-- 진행 구조
-- ---------------------------------------------------------------------------
CREATE TABLE "진행순서" (
    "번호"      INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호" INTEGER  NOT NULL,
    "순서"      INTEGER  NOT NULL,
    "진행시간"  INTEGER  NOT NULL DEFAULT 30,
    CONSTRAINT "pk_진행순서"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_진행순서_작품_순서" UNIQUE ("작품_번호", "순서"),
    CONSTRAINT "fk_진행순서_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "ck_진행순서_순서"      CHECK ("순서" >= 1),
    CONSTRAINT "ck_진행순서_진행시간"  CHECK ("진행시간" >= 0)
);

CREATE TABLE "진행구성" (
    "번호"            INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호"       INTEGER  NOT NULL,
    "진행순서_순서"   INTEGER  NOT NULL,
    "진행단계_번호"   INTEGER  NOT NULL,
    CONSTRAINT "pk_진행구성"                   PRIMARY KEY ("번호"),
    CONSTRAINT "uq_진행구성_작품_순서_단계"    UNIQUE ("작품_번호", "진행순서_순서", "진행단계_번호"),
    CONSTRAINT "fk_진행구성_작품"              FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_진행구성_진행순서"          FOREIGN KEY ("작품_번호", "진행순서_순서")
        REFERENCES "진행순서" ("작품_번호", "순서") ON DELETE CASCADE,
    CONSTRAINT "fk_진행구성_진행단계"          FOREIGN KEY ("진행단계_번호")
        REFERENCES "진행단계" ("번호") ON DELETE RESTRICT
);

CREATE INDEX "ix_진행구성_진행단계" ON "진행구성" ("진행단계_번호");

CREATE TABLE "기믹적용" (
    "번호"          INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호"     INTEGER  NOT NULL,
    "순서"          INTEGER  NOT NULL,
    "기믹_번호"     INTEGER  NOT NULL,
    "진행순서_순서" INTEGER  NOT NULL,
    CONSTRAINT "pk_기믹적용"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_기믹적용_작품_순서" UNIQUE ("작품_번호", "순서"),
    CONSTRAINT "fk_기믹적용_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_기믹적용_기믹"      FOREIGN KEY ("기믹_번호")
        REFERENCES "기믹" ("번호") ON DELETE RESTRICT,
    CONSTRAINT "fk_기믹적용_진행순서"  FOREIGN KEY ("작품_번호", "진행순서_순서")
        REFERENCES "진행순서" ("작품_번호", "순서") ON DELETE RESTRICT,
    CONSTRAINT "ck_기믹적용_순서"      CHECK ("순서" >= 1)
);

CREATE INDEX "ix_기믹적용_기믹"     ON "기믹적용" ("기믹_번호");
CREATE INDEX "ix_기믹적용_진행순서" ON "기믹적용" ("작품_번호", "진행순서_순서");

-- ---------------------------------------------------------------------------
-- 인물 / 관계 / 장소
-- ---------------------------------------------------------------------------
CREATE TABLE "인물" (
    "번호"      INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호" INTEGER  NOT NULL,
    "순서"      INTEGER  NOT NULL,
    "이름"      TEXT     NOT NULL,
    "직업"      TEXT,
    "나이"      INTEGER,
    "성별"      TEXT,
    "서사"      TEXT     NOT NULL,
    "타임라인"  TEXT,
    "능력"      TEXT,
    "비밀"      TEXT,
    "목표"      TEXT,
    "범인"      BOOLEAN  NOT NULL DEFAULT FALSE,
    "NPC"       BOOLEAN  NOT NULL DEFAULT FALSE,
    CONSTRAINT "pk_인물"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_인물_작품_순서" UNIQUE ("작품_번호", "순서"),
    CONSTRAINT "fk_인물_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "ck_인물_순서"      CHECK ("순서" >= 1)
);

CREATE TABLE "관계" (
    "번호"            INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호"       INTEGER  NOT NULL,
    "인물_순서"       INTEGER  NOT NULL,
    "대상_인물_순서"  INTEGER  NOT NULL,
    "관계"            TEXT     NOT NULL,
    CONSTRAINT "pk_관계"          PRIMARY KEY ("번호"),
    CONSTRAINT "fk_관계_작품"     FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_관계_인물"     FOREIGN KEY ("작품_번호", "인물_순서")
        REFERENCES "인물" ("작품_번호", "순서") ON DELETE CASCADE,
    CONSTRAINT "fk_관계_대상인물" FOREIGN KEY ("작품_번호", "대상_인물_순서")
        REFERENCES "인물" ("작품_번호", "순서") ON DELETE CASCADE
);

CREATE INDEX "ix_관계_인물"     ON "관계" ("작품_번호", "인물_순서");
CREATE INDEX "ix_관계_대상인물" ON "관계" ("작품_번호", "대상_인물_순서");

CREATE TABLE "장소" (
    "번호"            INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호"       INTEGER  NOT NULL,
    "순서"            INTEGER  NOT NULL,
    "상위_장소_순서"  INTEGER,
    "이름"            TEXT     NOT NULL,
    "유형"            TEXT,
    "특징"            TEXT,
    CONSTRAINT "pk_장소"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_장소_작품_순서" UNIQUE ("작품_번호", "순서"),
    CONSTRAINT "fk_장소_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_장소_상위장소"  FOREIGN KEY ("작품_번호", "상위_장소_순서")
        REFERENCES "장소" ("작품_번호", "순서") ON DELETE RESTRICT,
    CONSTRAINT "ck_장소_순서"      CHECK ("순서" >= 1)
);

CREATE INDEX "ix_장소_상위장소" ON "장소" ("작품_번호", "상위_장소_순서");

-- ---------------------------------------------------------------------------
-- 단서 / 증언 / 조합
-- ---------------------------------------------------------------------------
CREATE TABLE "단서" (
    "번호"      INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호" INTEGER  NOT NULL,
    "순서"      INTEGER  NOT NULL,
    "이름"      TEXT     NOT NULL,
    "내용"      TEXT,
    "기능"      TEXT,
    "인물_순서" INTEGER,
    "장소_순서" INTEGER,
    CONSTRAINT "pk_단서"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_단서_작품_순서" UNIQUE ("작품_번호", "순서"),
    CONSTRAINT "fk_단서_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_단서_인물"      FOREIGN KEY ("작품_번호", "인물_순서")
        REFERENCES "인물" ("작품_번호", "순서") ON DELETE RESTRICT,
    CONSTRAINT "fk_단서_장소"      FOREIGN KEY ("작품_번호", "장소_순서")
        REFERENCES "장소" ("작품_번호", "순서") ON DELETE RESTRICT,
    CONSTRAINT "ck_단서_순서"      CHECK ("순서" >= 1)
);

CREATE INDEX "ix_단서_인물" ON "단서" ("작품_번호", "인물_순서");
CREATE INDEX "ix_단서_장소" ON "단서" ("작품_번호", "장소_순서");

CREATE TABLE "증언" (
    "번호"      INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호" INTEGER  NOT NULL,
    "순서"      INTEGER  NOT NULL,
    "화자"      TEXT     NOT NULL,
    "내용"      TEXT     NOT NULL,
    "인물_순서" INTEGER,
    "장소_순서" INTEGER,
    CONSTRAINT "pk_증언"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_증언_작품_순서" UNIQUE ("작품_번호", "순서"),
    CONSTRAINT "fk_증언_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_증언_인물"      FOREIGN KEY ("작품_번호", "인물_순서")
        REFERENCES "인물" ("작품_번호", "순서") ON DELETE RESTRICT,
    CONSTRAINT "fk_증언_장소"      FOREIGN KEY ("작품_번호", "장소_순서")
        REFERENCES "장소" ("작품_번호", "순서") ON DELETE RESTRICT,
    CONSTRAINT "ck_증언_순서"      CHECK ("순서" >= 1)
);

CREATE INDEX "ix_증언_인물" ON "증언" ("작품_번호", "인물_순서");
CREATE INDEX "ix_증언_장소" ON "증언" ("작품_번호", "장소_순서");

CREATE TABLE "조합" (
    "번호"      INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호" INTEGER  NOT NULL,
    "순서"      INTEGER  NOT NULL,
    "이름"      TEXT     NOT NULL,
    "내용"      TEXT,
    "기능"      TEXT,
    CONSTRAINT "pk_조합"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_조합_작품_순서" UNIQUE ("작품_번호", "순서"),
    CONSTRAINT "fk_조합_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "ck_조합_순서"      CHECK ("순서" >= 1)
);

CREATE TABLE "조합재료" (
    "번호"              INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호"         INTEGER  NOT NULL,
    "결과_조합_순서"    INTEGER  NOT NULL,
    "단서_순서"         INTEGER,
    "증언_순서"         INTEGER,
    "조합_순서"         INTEGER,
    CONSTRAINT "pk_조합재료"          PRIMARY KEY ("번호"),
    CONSTRAINT "fk_조합재료_작품"     FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_조합재료_결과조합" FOREIGN KEY ("작품_번호", "결과_조합_순서")
        REFERENCES "조합" ("작품_번호", "순서") ON DELETE CASCADE,
    CONSTRAINT "fk_조합재료_단서"     FOREIGN KEY ("작품_번호", "단서_순서")
        REFERENCES "단서" ("작품_번호", "순서") ON DELETE RESTRICT,
    CONSTRAINT "fk_조합재료_증언"     FOREIGN KEY ("작품_번호", "증언_순서")
        REFERENCES "증언" ("작품_번호", "순서") ON DELETE RESTRICT,
    CONSTRAINT "fk_조합재료_조합"     FOREIGN KEY ("작품_번호", "조합_순서")
        REFERENCES "조합" ("작품_번호", "순서") ON DELETE RESTRICT,
    -- 한 행은 단서·증언·조합 중 정확히 하나만 가리킨다. (확정: 정확히 1개)
    CONSTRAINT "ck_조합재료_재료하나" CHECK (num_nonnulls("단서_순서", "증언_순서", "조합_순서") = 1)
);

CREATE INDEX "ix_조합재료_결과조합" ON "조합재료" ("작품_번호", "결과_조합_순서");
CREATE INDEX "ix_조합재료_단서"     ON "조합재료" ("작품_번호", "단서_순서");
CREATE INDEX "ix_조합재료_증언"     ON "조합재료" ("작품_번호", "증언_순서");
CREATE INDEX "ix_조합재료_조합"     ON "조합재료" ("작품_번호", "조합_순서");

-- ---------------------------------------------------------------------------
-- 사건 / 타임라인 / 엔딩분기 / 후일담
-- ---------------------------------------------------------------------------
CREATE TABLE "사건" (
    "번호"      INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호" INTEGER  NOT NULL,
    "순서"      INTEGER  NOT NULL,
    "설명"      TEXT,
    CONSTRAINT "pk_사건"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_사건_작품_순서" UNIQUE ("작품_번호", "순서"),
    CONSTRAINT "fk_사건_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "ck_사건_순서"      CHECK ("순서" >= 1)
);

CREATE TABLE "사건설명" (
    "번호"          INTEGER    GENERATED ALWAYS AS IDENTITY,
    "작품_번호"     INTEGER    NOT NULL,
    "사건_순서"     INTEGER    NOT NULL,
    "인물_순서"     INTEGER,
    "상태"          TEXT,
    "설명"          TEXT,
    "추정발생시간"  TIMESTAMP,
    "추정종료시간"  TIMESTAMP,
    CONSTRAINT "pk_사건설명"       PRIMARY KEY ("번호"),
    CONSTRAINT "fk_사건설명_작품"  FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_사건설명_사건"  FOREIGN KEY ("작품_번호", "사건_순서")
        REFERENCES "사건" ("작품_번호", "순서") ON DELETE CASCADE,
    CONSTRAINT "fk_사건설명_인물"  FOREIGN KEY ("작품_번호", "인물_순서")
        REFERENCES "인물" ("작품_번호", "순서") ON DELETE RESTRICT
);

CREATE INDEX "ix_사건설명_사건" ON "사건설명" ("작품_번호", "사건_순서");
CREATE INDEX "ix_사건설명_인물" ON "사건설명" ("작품_번호", "인물_순서");

CREATE TABLE "타임라인" (
    "번호"      INTEGER    GENERATED ALWAYS AS IDENTITY,
    "작품_번호" INTEGER    NOT NULL,
    "순서"      INTEGER    NOT NULL,
    "시작시간"  TIMESTAMP,
    "종료시간"  TIMESTAMP,
    "설명"      TEXT       NOT NULL,
    CONSTRAINT "pk_타임라인"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_타임라인_작품_순서" UNIQUE ("작품_번호", "순서"),
    CONSTRAINT "fk_타임라인_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "ck_타임라인_순서"      CHECK ("순서" >= 1)
);

CREATE TABLE "엔딩분기" (
    "번호"      INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호" INTEGER  NOT NULL,
    "순서"      INTEGER  NOT NULL,
    "조건"      JSONB    NOT NULL,
    "내용"      TEXT     NOT NULL,
    CONSTRAINT "pk_엔딩분기"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_엔딩분기_작품_순서" UNIQUE ("작품_번호", "순서"),
    CONSTRAINT "fk_엔딩분기_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "ck_엔딩분기_순서"      CHECK ("순서" >= 1)
);

CREATE TABLE "후일담" (
    "번호"      INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호" INTEGER  NOT NULL,
    "순서"      INTEGER  NOT NULL,
    "인물_순서" INTEGER,
    "조건"      JSONB,
    "내용"      TEXT     NOT NULL,
    CONSTRAINT "pk_후일담"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_후일담_작품_순서" UNIQUE ("작품_번호", "순서"),
    CONSTRAINT "fk_후일담_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_후일담_인물"      FOREIGN KEY ("작품_번호", "인물_순서")
        REFERENCES "인물" ("작품_번호", "순서") ON DELETE RESTRICT,
    CONSTRAINT "ck_후일담_순서"      CHECK ("순서" >= 1)
);

CREATE INDEX "ix_후일담_인물" ON "후일담" ("작품_번호", "인물_순서");

-- ---------------------------------------------------------------------------
-- 투표 / 미디어
-- ---------------------------------------------------------------------------
CREATE TABLE "투표" (
    "번호"          INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호"     INTEGER  NOT NULL,
    "순서"          INTEGER  NOT NULL,
    "진행순서_순서" INTEGER  NOT NULL,
    "이름"          TEXT     NOT NULL,
    "내용"          TEXT     NOT NULL,
    "규칙"          JSONB    NOT NULL,
    CONSTRAINT "pk_투표"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_투표_작품_순서" UNIQUE ("작품_번호", "순서"),
    CONSTRAINT "fk_투표_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_투표_진행순서"  FOREIGN KEY ("작품_번호", "진행순서_순서")
        REFERENCES "진행순서" ("작품_번호", "순서") ON DELETE RESTRICT,
    CONSTRAINT "ck_투표_순서"      CHECK ("순서" >= 1)
);

CREATE INDEX "ix_투표_진행순서" ON "투표" ("작품_번호", "진행순서_순서");

CREATE TABLE "미디어" (
    "번호"          INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호"     INTEGER  NOT NULL,
    "순서"          INTEGER  NOT NULL,
    "단서_순서"     INTEGER,
    "증언_순서"     INTEGER,
    "조합_순서"     INTEGER,
    "진행순서_순서" INTEGER,
    "조건"          JSONB,
    "유형"          TEXT     NOT NULL,
    "경로"          TEXT     NOT NULL,
    CONSTRAINT "pk_미디어"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_미디어_작품_순서" UNIQUE ("작품_번호", "순서"),
    CONSTRAINT "fk_미디어_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_미디어_단서"      FOREIGN KEY ("작품_번호", "단서_순서")
        REFERENCES "단서" ("작품_번호", "순서") ON DELETE RESTRICT,
    CONSTRAINT "fk_미디어_증언"      FOREIGN KEY ("작품_번호", "증언_순서")
        REFERENCES "증언" ("작품_번호", "순서") ON DELETE RESTRICT,
    CONSTRAINT "fk_미디어_조합"      FOREIGN KEY ("작품_번호", "조합_순서")
        REFERENCES "조합" ("작품_번호", "순서") ON DELETE RESTRICT,
    CONSTRAINT "fk_미디어_진행순서"  FOREIGN KEY ("작품_번호", "진행순서_순서")
        REFERENCES "진행순서" ("작품_번호", "순서") ON DELETE RESTRICT,
    CONSTRAINT "ck_미디어_순서"      CHECK ("순서" >= 1),
    CONSTRAINT "ck_미디어_유형"      CHECK ("유형" IN ('이미지', '영상'))
);

CREATE INDEX "ix_미디어_단서"     ON "미디어" ("작품_번호", "단서_순서");
CREATE INDEX "ix_미디어_증언"     ON "미디어" ("작품_번호", "증언_순서");
CREATE INDEX "ix_미디어_조합"     ON "미디어" ("작품_번호", "조합_순서");
CREATE INDEX "ix_미디어_진행순서" ON "미디어" ("작품_번호", "진행순서_순서");
