-- 게임 채팅 기록 (사용자 결정 2026-10-18).
-- 게임 안에는 채팅 장소가 있다(전체, 밀담 A, 밀담 B …). 플레이어는 한 번에 한 장소에만 있고, 메시지는 보낼 때 그 장소에 있던
-- 사람에게만 보인다(밀담실의 인원은 2명까지). 그래서 메시지마다 "누가 받았는지"를 남긴다(대화수신). 장소에 나중에 들어온 사람은
-- 이전 메시지를 받지 못하고, 다른 장소에 가 있던 동안의 메시지도 받지 못한다. 관전자는 받는 사람이 아니고 서버가 보는 사람의 종류에
-- 따라 거른다(일반 관전: 전체 장소만, GM 관전: 모두).

CREATE TABLE "대화" (
    "번호"      INTEGER      GENERATED ALWAYS AS IDENTITY,
    "진행_번호" INTEGER      NOT NULL,
    "계정_번호" INTEGER      NOT NULL,
    "장소"      TEXT         NOT NULL,
    "내용"      TEXT         NOT NULL,
    "보낸일시"  TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "pk_대화"        PRIMARY KEY ("번호"),
    CONSTRAINT "fk_대화_진행"   FOREIGN KEY ("진행_번호")
        REFERENCES "진행" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_대화_계정"   FOREIGN KEY ("계정_번호")
        REFERENCES "계정" ("번호") ON DELETE RESTRICT,
    CONSTRAINT "ck_대화_내용"   CHECK (char_length("내용") BETWEEN 1 AND 500)
);

CREATE INDEX "ix_대화_진행" ON "대화" ("진행_번호", "번호");
CREATE INDEX "ix_대화_계정" ON "대화" ("계정_번호");

CREATE TABLE "대화수신" (
    "번호"      INTEGER  GENERATED ALWAYS AS IDENTITY,
    "대화_번호" INTEGER  NOT NULL,
    "계정_번호" INTEGER  NOT NULL,
    CONSTRAINT "pk_대화수신"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_대화수신_대화_계정" UNIQUE ("대화_번호", "계정_번호"),
    CONSTRAINT "fk_대화수신_대화"      FOREIGN KEY ("대화_번호")
        REFERENCES "대화" ("번호") ON DELETE CASCADE,
    CONSTRAINT "fk_대화수신_계정"      FOREIGN KEY ("계정_번호")
        REFERENCES "계정" ("번호") ON DELETE RESTRICT
);

CREATE INDEX "ix_대화수신_계정" ON "대화수신" ("계정_번호", "대화_번호");
