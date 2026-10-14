-- 0010_rename_tester_table.sql
-- 명세서 변경(사용자 결정, 2026-10-14): 테이블 "작품테스터" 의 이름을 "테스터" 로 바꾼다.
-- 0008 은 이미 적용된 파일이라 고치지 않고 새 마이그레이션으로 이름을 바꾼다.
-- 제약조건·인덱스·시퀀스 이름도 새 테이블 이름에 맞춘다 (다른 테이블과 같은 명명 규칙).

ALTER TABLE "작품테스터" RENAME TO "테스터";

ALTER TABLE "테스터" RENAME CONSTRAINT "pk_작품테스터"           TO "pk_테스터";
ALTER TABLE "테스터" RENAME CONSTRAINT "uq_작품테스터_작품_계정" TO "uq_테스터_작품_계정";
ALTER TABLE "테스터" RENAME CONSTRAINT "fk_작품테스터_작품"      TO "fk_테스터_작품";
ALTER TABLE "테스터" RENAME CONSTRAINT "fk_작품테스터_계정"      TO "fk_테스터_계정";

ALTER INDEX "ix_작품테스터_계정" RENAME TO "ix_테스터_계정";
ALTER SEQUENCE "작품테스터_번호_seq" RENAME TO "테스터_번호_seq";
