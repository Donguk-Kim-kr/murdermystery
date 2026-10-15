-- 0012_library_share_flag.sql
-- 영역: 재사용 라이브러리 (진행단계 / 기믹) 공개 여부
-- 기준: db/spec/schema_spec.xlsx (시트 '진행단계', '기믹')
--
-- 설계 (사용자 결정, 2026-10-15)
--  * 나중에 제작자끼리 기믹·진행단계를 공유할 수 있도록 "공개여부" 컬럼을 미리 둔다.
--    지금은 쓰이는 곳이 없다: 선택 목록은 계속 "공통 항목(계정_번호 NULL)과 본인 것"만 보여 준다.
--    공유 기능을 만들 때 "공개여부가 TRUE 인 다른 제작자의 항목"을 목록에 추가한다.
--  * 기본값은 FALSE(공개하지 않음). "계정_번호"가 NULL 인 공통 항목은 공개여부와 무관하게 모두에게 보인다.
--  * 버전 행마다 따로 가진다. v1 은 공개하고 v2 는 공개하지 않을 수 있다.
--  * 공개 여부는 켜고 끌 수 있어야 하므로, 0011 의 불변 트리거에서 "삭제일시"와 함께 수정 가능한 컬럼으로 뺀다.
--    나머지 컬럼은 계속 수정할 수 없고, 삭제 표시는 한 번만 할 수 있다.

ALTER TABLE "진행단계" ADD COLUMN "공개여부" BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE "기믹"     ADD COLUMN "공개여부" BOOLEAN NOT NULL DEFAULT FALSE;

CREATE OR REPLACE FUNCTION "fn_라이브러리_불변"() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    -- 삭제일시·공개여부를 제외한 나머지 컬럼은 바꿀 수 없다.
    IF (to_jsonb(NEW) - '삭제일시' - '공개여부') IS DISTINCT FROM (to_jsonb(OLD) - '삭제일시' - '공개여부') THEN
        RAISE EXCEPTION '"%"의 행은 수정할 수 없습니다. 같은 이름으로 버전을 올려 새 행을 추가하세요. (번호=%)',
            TG_TABLE_NAME, OLD."번호"
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    -- 삭제일시는 NULL 에서 값으로만 바꿀 수 있다. (삭제 취소·삭제 시각 변경 불가)
    IF NEW."삭제일시" IS DISTINCT FROM OLD."삭제일시" THEN
        IF OLD."삭제일시" IS NOT NULL OR NEW."삭제일시" IS NULL THEN
            RAISE EXCEPTION '"%"의 삭제 표시는 한 번만 할 수 있으며 되돌릴 수 없습니다. (번호=%)',
                TG_TABLE_NAME, OLD."번호"
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
