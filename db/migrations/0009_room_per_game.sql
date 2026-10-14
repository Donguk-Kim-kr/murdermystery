-- 0009_room_per_game.sql
-- 영역: 방 / 진행
-- 명세서 변경(사용자 결정, 2026-10-14): 1방 N판 → **1방 1게임**.
--   * 방을 만들 때 작품을 고르고, 그 작품의 **확정된 최신 버전**이 자동으로 정해져 "방"에 저장된다.
--     (최신 버전을 고르는 일은 백엔드가 한다. 버전 문자열은 비교하지 않고 "버전"."번호"가 가장 큰 행을 쓴다.)
--   * "진행"은 방마다 하나뿐이다. 진행의 작품·버전은 방의 것과 같아야 한다 (복합 FK 로 DB 가 보장).
--   * 이로써 "한 방의 동시 진행 1개 제한"(DB_RULES B23, 미결정 4번)은 필요 없어진다.
-- 주의: "방"에 NOT NULL 컬럼을 기본값 없이 추가하므로 기존 방 행이 있으면 실패한다. 방 기능을 만들기 전이라 행이 없다.

ALTER TABLE "방" ADD COLUMN "작품_번호" INTEGER NOT NULL;
ALTER TABLE "방" ADD COLUMN "버전_버전" TEXT    NOT NULL;

ALTER TABLE "방"
    ADD CONSTRAINT "fk_방_작품" FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE RESTRICT,
    ADD CONSTRAINT "fk_방_버전" FOREIGN KEY ("작품_번호", "버전_버전")
        REFERENCES "버전" ("작품_번호", "버전") ON DELETE RESTRICT,
    -- 진행이 (방, 작품, 버전) 세 값을 한 번에 가리킬 수 있도록 하는 대상 키
    ADD CONSTRAINT "uq_방_번호_작품_버전" UNIQUE ("번호", "작품_번호", "버전_버전");

CREATE INDEX "ix_방_버전" ON "방" ("작품_번호", "버전_버전");

ALTER TABLE "진행"
    ADD CONSTRAINT "uq_진행_방" UNIQUE ("방_번호"),
    ADD CONSTRAINT "fk_진행_방_작품_버전" FOREIGN KEY ("방_번호", "작품_번호", "버전_버전")
        REFERENCES "방" ("번호", "작품_번호", "버전_버전") ON DELETE RESTRICT;

CREATE INDEX "ix_진행_방_작품_버전" ON "진행" ("방_번호", "작품_번호", "버전_버전");
