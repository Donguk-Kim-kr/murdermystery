-- 작품 표지 이미지 (사용자 결정 2026-10-21).
-- 작품 목록·플레이 기록에 보이는 대표 이미지이다. `미디어` 의 연결 대상에 작품 자체(표지)를 더한다.
-- * 표지: TRUE 이면 작품의 표지 이미지이다. 작품당 하나뿐이라 번호 칸은 없다(한 건만 두는 것은 서버가 지킨다. 공통스토리와 같다).
-- * 연결 대상은 여전히 **정확히 하나**여야 한다(단서·증언·조합·진행순서·인물 중 하나, 공통스토리, 표지).
-- 표지는 확정한 시나리오(스냅샷)에 담기지 않는다. 작품 목록에 보이는 작품 자체의 정보이기 때문이다(서버가 정한 규칙, docs/DB_RULES.md B41).

ALTER TABLE "미디어" ADD COLUMN "표지" BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE "미디어" DROP CONSTRAINT "ck_미디어_대상";
ALTER TABLE "미디어" ADD CONSTRAINT "ck_미디어_대상"
    CHECK (num_nonnulls("단서_순서", "증언_순서", "조합_순서", "진행순서_순서", "인물_순서")
           + CASE WHEN "공통스토리" THEN 1 ELSE 0 END + CASE WHEN "표지" THEN 1 ELSE 0 END = 1);
