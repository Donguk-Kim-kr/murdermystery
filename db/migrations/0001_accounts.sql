-- 0001_accounts.sql
-- 영역: 계정 / 로그인 세션
-- 기준: db/spec/schema_spec.xlsx (시트 '계정', '로그인세션')
-- 규칙: 한글 테이블명·컬럼명을 그대로 유지하며, 모든 식별자는 큰따옴표로 감싼다.
--       기본키 "번호"는 INTEGER GENERATED ALWAYS AS IDENTITY 이다.

CREATE TABLE "계정" (
    "번호"     INTEGER       GENERATED ALWAYS AS IDENTITY,
    "아이디"   TEXT          NOT NULL,
    "패스워드" TEXT          NOT NULL,
    "닉네임"   TEXT          NOT NULL,
    "가입일시" TIMESTAMPTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "상태"     TEXT          NOT NULL DEFAULT '정상',
    CONSTRAINT "pk_계정"        PRIMARY KEY ("번호"),
    CONSTRAINT "uq_계정_아이디" UNIQUE ("아이디"),
    CONSTRAINT "ck_계정_상태"   CHECK ("상태" IN ('정상', '정지', '탈퇴'))
);

CREATE TABLE "로그인세션" (
    "번호"      INTEGER       GENERATED ALWAYS AS IDENTITY,
    "계정_번호" INTEGER       NOT NULL,
    "토큰"      TEXT          NOT NULL,
    "생성일시"  TIMESTAMPTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "만료일시"  TIMESTAMPTZ   NOT NULL,
    "폐기일시"  TIMESTAMPTZ,
    "접속환경"  TEXT          NOT NULL,
    CONSTRAINT "pk_로그인세션"        PRIMARY KEY ("번호"),
    CONSTRAINT "uq_로그인세션_토큰"   UNIQUE ("토큰"),
    CONSTRAINT "fk_로그인세션_계정"   FOREIGN KEY ("계정_번호")
        REFERENCES "계정" ("번호") ON DELETE CASCADE,
    CONSTRAINT "ck_로그인세션_만료"   CHECK ("만료일시" > "생성일시"),
    CONSTRAINT "ck_로그인세션_환경"   CHECK ("접속환경" IN ('PC', '모바일'))
);

CREATE INDEX "ix_로그인세션_계정" ON "로그인세션" ("계정_번호");
