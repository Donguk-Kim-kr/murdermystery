-- 단서 공개 기록 (사용자 결정 2026-10-17: 토론에서 단서를 한 명·여러 명·전체에게 보여 줄 수 있고, 취소할 수 있다).
--
-- 한 행은 "이 획득(단서)을 이 사람에게 보여 주었다"는 기록이다. 대상이 비어 있으면 전체 공개이다.
-- 공개가 유효하다는 것은 취소일시가 비어 있고 걸린 획득의 보유여부가 켜져 있다는 뜻이다.
-- 단서를 양도하면 그 단서에 걸린 공개는 모두 취소된다(소유권이 바뀌므로).

CREATE TABLE "공개" (
    "번호"            INTEGER      GENERATED ALWAYS AS IDENTITY,
    "작품_번호"       INTEGER      NOT NULL,
    "진행_번호"       INTEGER      NOT NULL,
    "획득_번호"       INTEGER      NOT NULL,
    "대상_참여_번호"  INTEGER,
    "공개일시"        TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "취소일시"        TIMESTAMPTZ,
    CONSTRAINT "pk_공개"       PRIMARY KEY ("번호"),
    CONSTRAINT "fk_공개_작품"  FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE RESTRICT,
    CONSTRAINT "fk_공개_진행"  FOREIGN KEY ("진행_번호")
        REFERENCES "진행" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_공개_획득"  FOREIGN KEY ("획득_번호")
        REFERENCES "획득" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_공개_참여"  FOREIGN KEY ("대상_참여_번호")
        REFERENCES "참여" ("번호") ON DELETE CASCADE
);

CREATE INDEX "ix_공개_작품" ON "공개" ("작품_번호");
CREATE INDEX "ix_공개_진행" ON "공개" ("진행_번호");
CREATE INDEX "ix_공개_획득" ON "공개" ("획득_번호");
CREATE INDEX "ix_공개_참여" ON "공개" ("대상_참여_번호");
