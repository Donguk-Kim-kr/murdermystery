-- 미디어(이미지·영상)를 인물과 공통 스토리에도 붙인다 (사용자 결정 2026-10-20).
-- 지금까지 연결 대상은 단서·증언·조합·진행순서뿐이라 캐릭터 이미지와 공통 스토리 영상을 담을 칸이 없었다.
-- * 인물_순서: 캐릭터 이미지. 복합 FK 로 같은 작품의 인물만 가리킨다(다른 연결과 같은 RESTRICT).
-- * 공통스토리: TRUE 이면 작품의 공통 스토리에 붙는 미디어(영상). 작품당 대상이 하나뿐이라 번호 칸은 없다.
-- * 연결 대상은 **정확히 하나**여야 한다(없는 미디어나 여러 곳에 걸친 미디어는 화면에서 쓸 수 없다). 지금까지 미디어는 한 건도 없어 데이터 변환은 없다.

ALTER TABLE "미디어" ADD COLUMN "인물_순서" INTEGER;
ALTER TABLE "미디어" ADD COLUMN "공통스토리" BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE "미디어" ADD CONSTRAINT "fk_미디어_인물"
    FOREIGN KEY ("작품_번호", "인물_순서") REFERENCES "인물" ("작품_번호", "순서") ON DELETE RESTRICT;
CREATE INDEX "ix_미디어_인물" ON "미디어" ("작품_번호", "인물_순서");

ALTER TABLE "미디어" ADD CONSTRAINT "ck_미디어_대상"
    CHECK (num_nonnulls("단서_순서", "증언_순서", "조합_순서", "진행순서_순서", "인물_순서") + CASE WHEN "공통스토리" THEN 1 ELSE 0 END = 1);
