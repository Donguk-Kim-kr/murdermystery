-- 0011_library_versions.sql
-- 영역: 재사용 라이브러리 (진행단계 / 기믹) 버전 관리·변경내역·삭제 표시
-- 기준: db/spec/schema_spec.xlsx (시트 '진행단계', '기믹')
--
-- 설계 (사용자 결정, 2026-10-14)
--  * 라이브러리 항목을 고칠 때는 행을 수정하지 않고 같은 이름으로 "버전"을 올려 새 행을 추가한다.
--    같은 항목(계열)의 식별자는 ("계정_번호", "이름") 이고, 버전은 그 안에서 1, 2, 3 ... 이다.
--    같은 제작자가 같은 이름으로 만든 두 번째 행이 곧 새 버전이다. 이름을 바꾸면 다른 계열이 된다.
--  * "계정_번호"가 NULL 인 공통(시스템 제공) 항목도 같은 규칙을 쓰도록 NULLS NOT DISTINCT 로 만든다.
--    (PostgreSQL 은 기본적으로 NULL 을 서로 다른 값으로 보므로 일반 UNIQUE 로는 공통 항목의 중복을 막지 못한다.)
--  * "변경내역"은 이 버전에서 무엇이 바뀌었는지 적는 글이다. 제작자가 항목을 고를 때 보여 주기 위한 것이다.
--  * 삭제는 행을 지우지 않는 "삭제 표시"이다. "삭제일시"가 NULL 이 아니면 삭제된 항목이며,
--    새로 선택할 수 없고 기존 작품에서는 '삭제된 항목'으로 취급한다. 행과 이미 확정된 스냅샷은 그대로 남는다.
--    삭제된 항목의 이름·버전은 계속 점유되므로 같은 이름·버전을 다시 만들 수 없다.
--  * 작품의 "진행구성"/"기믹적용"은 특정 버전의 행 "번호"를 가리킨다. 새 버전이 나와도
--    작품이 가리키는 행은 바뀌지 않으며, 작품이 새 버전을 쓰려면 가리키는 행을 바꿔야 한다.
--  * 그러려면 행 내용이 바뀌지 않아야 하므로, "삭제일시"를 NULL -> 값으로 바꾸는 것 외의 UPDATE 는 막는다.
--    (삭제 취소도 막는다. 필요해지면 트리거를 완화한다.) 물리적 삭제는 기존 FK 가 보호한다.
--  * 기존 행은 ("계정_번호", "이름")이 같은 것끼리 "번호" 순으로 버전 1, 2, 3 ... 을 받는다.

ALTER TABLE "진행단계"
    ADD COLUMN "버전"     INTEGER     NOT NULL DEFAULT 1,
    ADD COLUMN "변경내역" TEXT,
    ADD COLUMN "삭제일시" TIMESTAMPTZ;

ALTER TABLE "기믹"
    ADD COLUMN "버전"     INTEGER     NOT NULL DEFAULT 1,
    ADD COLUMN "변경내역" TEXT,
    ADD COLUMN "삭제일시" TIMESTAMPTZ;

UPDATE "진행단계" t SET "버전" = r.rn
FROM (SELECT "번호", ROW_NUMBER() OVER (PARTITION BY "계정_번호", "이름" ORDER BY "번호") AS rn
      FROM "진행단계") r
WHERE t."번호" = r."번호";

UPDATE "기믹" t SET "버전" = r.rn
FROM (SELECT "번호", ROW_NUMBER() OVER (PARTITION BY "계정_번호", "이름" ORDER BY "번호") AS rn
      FROM "기믹") r
WHERE t."번호" = r."번호";

ALTER TABLE "진행단계"
    ADD CONSTRAINT "ck_진행단계_버전" CHECK ("버전" >= 1),
    ADD CONSTRAINT "uq_진행단계_계정_이름_버전" UNIQUE NULLS NOT DISTINCT ("계정_번호", "이름", "버전");

ALTER TABLE "기믹"
    ADD CONSTRAINT "ck_기믹_버전" CHECK ("버전" >= 1),
    ADD CONSTRAINT "uq_기믹_계정_이름_버전" UNIQUE NULLS NOT DISTINCT ("계정_번호", "이름", "버전");

CREATE FUNCTION "fn_라이브러리_불변"() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    -- 삭제일시를 제외한 나머지 컬럼은 바꿀 수 없다.
    IF ROW(NEW.*) IS DISTINCT FROM ROW(OLD.*) THEN
        IF (to_jsonb(NEW) - '삭제일시') IS DISTINCT FROM (to_jsonb(OLD) - '삭제일시') THEN
            RAISE EXCEPTION '"%"의 행은 수정할 수 없습니다. 같은 이름으로 버전을 올려 새 행을 추가하세요. (번호=%)',
                TG_TABLE_NAME, OLD."번호"
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        -- 삭제일시는 NULL 에서 값으로만 바꿀 수 있다. (삭제 취소·삭제 시각 변경 불가)
        IF OLD."삭제일시" IS NOT NULL OR NEW."삭제일시" IS NULL THEN
            RAISE EXCEPTION '"%"의 삭제 표시는 한 번만 할 수 있으며 되돌릴 수 없습니다. (번호=%)',
                TG_TABLE_NAME, OLD."번호"
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER "tg_진행단계_불변"
    BEFORE UPDATE ON "진행단계"
    FOR EACH ROW EXECUTE FUNCTION "fn_라이브러리_불변"();

CREATE TRIGGER "tg_기믹_불변"
    BEFORE UPDATE ON "기믹"
    FOR EACH ROW EXECUTE FUNCTION "fn_라이브러리_불변"();
