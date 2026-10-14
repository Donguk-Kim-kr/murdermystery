-- 0006_triggers.sql
-- 명세서의 자연어 규칙 중 DB 에서 구현 가능한 것만 트리거로 옮긴다.
--  1) "버전": 확정 후 변경하지 않는 스냅샷 (명세서: '확정 후 변경하지 않음')
--  2) "방": 상태가 바뀔 때 상태변경일시 갱신, 종료로 바뀔 때 종료일시 기록
--  3) "진행": 종료로 바뀔 때 종료일시 기록
-- 그 외 규칙(최대인원 자동 갱신, 자동 종료 시간 등)은 백엔드 담당이며 docs/DB_RULES.md 에 정리한다.

-- ---------------------------------------------------------------------------
-- 1) 버전 스냅샷 불변성
--    시나리오 / 작품_번호 / 버전 은 INSERT 이후 변경할 수 없다.
--    (변경사항 은 수정 가능. 삭제는 FK 가 보호: 진행이 참조 중이면 삭제 불가)
-- ---------------------------------------------------------------------------
CREATE FUNCTION "fn_버전_불변"() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW."시나리오" IS DISTINCT FROM OLD."시나리오" THEN
        RAISE EXCEPTION '확정된 버전의 시나리오는 변경할 수 없습니다. (버전 번호=%)', OLD."번호"
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW."작품_번호" IS DISTINCT FROM OLD."작품_번호"
       OR NEW."버전" IS DISTINCT FROM OLD."버전" THEN
        RAISE EXCEPTION '확정된 버전의 작품_번호와 버전은 변경할 수 없습니다. (버전 번호=%)', OLD."번호"
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER "tg_버전_불변"
    BEFORE UPDATE ON "버전"
    FOR EACH ROW EXECUTE FUNCTION "fn_버전_불변"();

-- ---------------------------------------------------------------------------
-- 2) 방: 상태변경일시 / 종료일시
-- ---------------------------------------------------------------------------
CREATE FUNCTION "fn_방_시각"() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW."상태" IS DISTINCT FROM OLD."상태" THEN
        NEW."상태변경일시" := CURRENT_TIMESTAMP;
    END IF;
    IF NEW."상태" = '종료' AND NEW."종료일시" IS NULL THEN
        NEW."종료일시" := CURRENT_TIMESTAMP;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER "tg_방_시각"
    BEFORE INSERT OR UPDATE ON "방"
    FOR EACH ROW EXECUTE FUNCTION "fn_방_시각"();

-- ---------------------------------------------------------------------------
-- 3) 진행: 종료일시
-- ---------------------------------------------------------------------------
CREATE FUNCTION "fn_진행_시각"() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW."상태" = '종료' AND NEW."종료일시" IS NULL THEN
        NEW."종료일시" := CURRENT_TIMESTAMP;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER "tg_진행_시각"
    BEFORE INSERT OR UPDATE ON "진행"
    FOR EACH ROW EXECUTE FUNCTION "fn_진행_시각"();
