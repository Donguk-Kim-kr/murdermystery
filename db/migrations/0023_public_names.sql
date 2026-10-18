-- 단서·증언·조합에 "공개이름"을 둔다 (사용자 결정 2026-10-18).
--
-- 이름이 둘 필요하다. 남들에게 보여 주는 이름(공개이름, 예: "A의 서랍", 지나가던 사람)과 진짜 이름(이름, 예: "커터칼", "A의 마약소문").
--  * 단서·조합: 공개이름 칸을 더한다(비워 둘 수 있다). 이름은 진짜 이름이다.
--  * 증언: 화자가 남들에게 보이는 이름 역할이었으므로 `화자` 를 `공개이름` 으로 바꾸고(비워 둘 수 있다), 진짜 이름인 `이름` 을 더한다.
--    이미 있는 증언의 이름은 "<화자>의 증언" 으로 채운다(그 전에 화면에 보이던 이름).
-- 컬럼은 맨 끝에 붙인다(테이블을 가리키는 외래키가 많아 다시 만들지 않는다). 증언의 화자 칸은 제자리에서 이름만 바뀐다.

ALTER TABLE "단서" ADD COLUMN "공개이름" TEXT;
ALTER TABLE "조합" ADD COLUMN "공개이름" TEXT;

ALTER TABLE "증언" RENAME COLUMN "화자" TO "공개이름";
ALTER TABLE "증언" ALTER COLUMN "공개이름" DROP NOT NULL;
ALTER TABLE "증언" ADD COLUMN "이름" TEXT;
UPDATE "증언" SET "이름" = COALESCE("공개이름" || '의 증언', '증언 ' || "순서");
ALTER TABLE "증언" ALTER COLUMN "이름" SET NOT NULL;
