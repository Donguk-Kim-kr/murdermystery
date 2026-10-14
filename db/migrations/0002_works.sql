-- 0002_works.sql
-- 영역: 작품 / 버전(확정 스냅샷)
-- 기준: db/spec/schema_spec.xlsx (시트 '작품', '버전')
--
-- 설계 메모
--  * "작품"과 아래 0003~0004의 제작용 콘텐츠 테이블은 '편집 중인 원본'이다.
--  * "버전"."시나리오"(JSONB)는 확정 시점의 전체 게임 데이터를 보존하는 불변 스냅샷이며,
--    실제 게임(0005의 "진행")은 이 스냅샷을 기준으로 동작한다.
--  * JSONB 내부 구조는 확정되지 않았으므로 어떠한 형식 CHECK도 두지 않는다.

CREATE TABLE "작품" (
    "번호"      INTEGER       GENERATED ALWAYS AS IDENTITY,
    "제목"      TEXT          NOT NULL,
    "시놉시스"  TEXT          NOT NULL,
    "장르"      TEXT          NOT NULL,
    "최소인원"  INTEGER       NOT NULL DEFAULT 4,
    "최대인원"  INTEGER       NOT NULL DEFAULT 4,
    "예상시간"  TEXT          NOT NULL DEFAULT '3시간',
    "상태"      TEXT          NOT NULL DEFAULT '개발',
    "생성일시"  TIMESTAMPTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "수정일시"  TIMESTAMPTZ,
    "최신버전"  TEXT          NOT NULL DEFAULT '1.0',
    "계정_번호" INTEGER       NOT NULL,
    "공개여부"  BOOLEAN       NOT NULL DEFAULT FALSE,
    CONSTRAINT "pk_작품"          PRIMARY KEY ("번호"),
    CONSTRAINT "fk_작품_계정"     FOREIGN KEY ("계정_번호")
        REFERENCES "계정" ("번호") ON DELETE RESTRICT,
    CONSTRAINT "ck_작품_최소인원" CHECK ("최소인원" >= 1),
    CONSTRAINT "ck_작품_최대인원" CHECK ("최대인원" >= "최소인원"),
    CONSTRAINT "ck_작품_상태"     CHECK ("상태" IN ('수정', '개발', '완료'))
);

CREATE INDEX "ix_작품_계정" ON "작품" ("계정_번호");

CREATE TABLE "버전" (
    "번호"       INTEGER      GENERATED ALWAYS AS IDENTITY,
    "작품_번호"  INTEGER      NOT NULL,
    "시나리오"   JSONB        NOT NULL,
    "버전"       TEXT         NOT NULL DEFAULT '1.0',
    "생성일시"   TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "변경사항"   TEXT,
    CONSTRAINT "pk_버전"            PRIMARY KEY ("번호"),
    -- 복합 FK("진행"이 (작품_번호, 버전)을 참조)의 대상이 되는 복합 UNIQUE
    CONSTRAINT "uq_버전_작품_버전"  UNIQUE ("작품_번호", "버전"),
    CONSTRAINT "fk_버전_작품"       FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE
);
