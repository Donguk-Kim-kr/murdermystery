-- 0014_text_materials.sql
-- 영역: 제작용 콘텐츠 (자료: 기믹이 불러 쓰는 글)
-- 기준: db/spec/schema_spec.xlsx (시트 '자료')
--
-- 설계 (사용자 결정, 2026-10-15)
--  * "자료"는 작품에 딸린 글을 따로 저장하는 테이블이다. 기믹이 긴 글을 보여 줄 때 스크립트 안에
--    글을 직접 쓰지 않고 번호로 불러 쓰며, 같은 글을 여러 기믹이 재사용할 수 있다.
--    ("미디어"가 이미지·영상을 따로 두는 것과 같은 구조.)
--  * 공통 스토리는 "작품"."공통스토리", 개인 서사는 "인물"."서사"에 있다. 그 밖에 기믹으로 보여 줄 글이 이 테이블에 들어간다.
--  * 다른 콘텐츠 테이블처럼 "작품_번호"만 가진다. 제작자는 "작품"."계정_번호"로 알 수 있어서 계정 컬럼은 두지 않는다.
--  * "순서"는 작품 안에서 1부터 이어지는 번호이고, 확정 스냅샷 안에서 이 글을 가리키는 키로 쓰인다.
--  * "제목"은 제작자가 어떤 글인지 알아보고, 기믹과 설명 화면에서 글을 가리킬 때 쓴다.

CREATE TABLE "자료" (
    "번호"      INTEGER  GENERATED ALWAYS AS IDENTITY,
    "작품_번호" INTEGER  NOT NULL,
    "순서"      INTEGER  NOT NULL,
    "제목"      TEXT     NOT NULL,
    "내용"      TEXT     NOT NULL,
    CONSTRAINT "pk_자료"           PRIMARY KEY ("번호"),
    CONSTRAINT "uq_자료_작품_순서" UNIQUE ("작품_번호", "순서"),
    CONSTRAINT "fk_자료_작품"      FOREIGN KEY ("작품_번호")
        REFERENCES "작품" ("번호") ON DELETE CASCADE,
    CONSTRAINT "ck_자료_순서"      CHECK ("순서" >= 1)
);
