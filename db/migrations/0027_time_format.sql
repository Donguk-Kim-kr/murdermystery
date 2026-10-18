-- 작품마다 시간(타임라인·사건 설명의 시작·종료 시간 등)을 어디까지 적을지 고른다 (사용자 결정 2026-10-18).
-- 시간만 / 일까지 / 월까지 / 연도까지. 값은 그대로 TIMESTAMP 에 저장하고, 적지 않는 윗단위(연·월·일)는 2000-01-01 로 채운다.
-- 이미 만든 작품은 지금까지처럼 연도까지 보이게 하고, 새로 만드는 작품의 기본은 시간만이다.

ALTER TABLE "작품" ADD COLUMN "시간형식" TEXT NOT NULL DEFAULT '연도까지';
ALTER TABLE "작품" ADD CONSTRAINT "ck_작품_시간형식" CHECK ("시간형식" IN ('시간만', '일까지', '월까지', '연도까지'));
ALTER TABLE "작품" ALTER COLUMN "시간형식" SET DEFAULT '시간만';
