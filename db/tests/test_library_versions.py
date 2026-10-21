"""라이브러리(진행단계 / 기믹)의 버전·변경내역·삭제 표시·공개 여부 테스트 (0011, 0012)."""
from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

from builders import Builders
from helpers import MIGRATIONS_DIR, Db, admin_sql, migrate

# 두 테이블에 같은 규칙이 적용되므로 같은 테스트를 양쪽에 돌린다.
TABLES = {
    "진행단계": dict(content="규칙", other={"설명": "설명"}),
    "기믹": dict(content="조건", other={"결과": {"k": 1}}),
}


class LibraryVersionCases:
    table: str
    content: str
    other: dict

    def make(self, **kw):
        kw.setdefault(self.content, {"v": 1})
        for k, v in self.other.items():
            kw.setdefault(k, v)
        kw.setdefault("이름", f"항목{self.db.n()}")
        return self.ins(self.table, **kw)

    def update(self, row, assignments):
        return self.db.run(f'UPDATE "{self.table}" SET {assignments} WHERE "번호"={row}')

    def update_fails(self, row, assignments, contains="수정할 수 없습니다"):
        return self.db.fails(f'UPDATE "{self.table}" SET {assignments} WHERE "번호"={row}', contains)

    # ---- 버전 --------------------------------------------------------------
    def test_default_version_is_one_and_extra_columns_are_optional(self):
        r = self.make()
        self.assertEqual(
            self.db.val(f'SELECT "버전", "변경내역" IS NULL, "삭제일시" IS NULL FROM "{self.table}" WHERE "번호"={r}'),
            "1|t|t")

    def test_same_owner_and_name_needs_a_new_version(self):
        a = self.account()
        self.make(이름="전체 토론", 계정_번호=a)
        self.ins_fails(self.table, f"uq_{self.table}_계정_이름_버전", 이름="전체 토론", 계정_번호=a,
                       **{self.content: {}}, **self.other)
        v2 = self.make(이름="전체 토론", 계정_번호=a, 버전=2, 변경내역="시간을 10분으로")
        self.assertEqual(self.db.val(f'SELECT "변경내역" FROM "{self.table}" WHERE "번호"={v2}'), "시간을 10분으로")

    def test_common_items_without_owner_are_also_unique(self):
        # NULL 은 UNIQUE 에서 서로 다른 값으로 취급되므로 NULLS NOT DISTINCT 가 필요하다.
        self.make(이름="공통")
        self.ins_fails(self.table, f"uq_{self.table}_계정_이름_버전", 이름="공통",
                       **{self.content: {}}, **self.other)
        self.make(이름="공통", 버전=2)

    def test_other_owner_or_other_name_is_a_separate_lineage(self):
        a, b = self.account(), self.account()
        self.make(이름="밀담", 계정_번호=a)
        self.make(이름="밀담", 계정_번호=b)     # 다른 제작자는 같은 이름·버전 가능
        self.make(이름="밀담", 계정_번호=None)  # 공통 항목과도 별개
        self.make(이름="밀담 2", 계정_번호=a)   # 이름이 다르면 다른 계열

    def test_version_must_be_positive(self):
        self.ins_fails(self.table, f"ck_{self.table}_버전", 이름="x", 버전=0, **{self.content: {}}, **self.other)

    # ---- 불변 --------------------------------------------------------------
    def test_content_columns_cannot_be_updated(self):
        a = self.account()
        r = self.make(계정_번호=a, 변경내역="처음")
        for assignment in (
            f"\"{self.content}\"='{{\"v\": 2}}'::jsonb",
            "\"버전\"=9",
            "\"변경내역\"='고침'",
            "\"계정_번호\"=NULL",
        ):
            self.update_fails(r, assignment)
        self.assertEqual(self.db.val(f'SELECT "변경내역", "버전" FROM "{self.table}" WHERE "번호"={r}'), "처음|1")

    def test_update_that_changes_nothing_is_harmless(self):
        r = self.make()
        self.assertEqual(self.update(r, '"이름"="이름"').returncode, 0)

    # ---- 이름 변경 (0015) --------------------------------------------------
    def test_rename_is_allowed_and_keeps_every_other_column(self):
        a = self.account()
        r = self.make(이름="옛 이름", 계정_번호=a, 변경내역="처음")
        self.db.ok(f'UPDATE "{self.table}" SET "이름"=\'새 이름\' WHERE "번호"={r}')
        self.assertEqual(self.db.val(f'SELECT "이름", "버전", "변경내역" FROM "{self.table}" WHERE "번호"={r}'),
                         "새 이름|1|처음")
        self.update_fails(r, '"이름"=\'또 바뀜\', "버전"=5')

    def test_renaming_a_whole_lineage_in_one_statement_works(self):
        a = self.account()
        for v in (1, 2, 3):
            self.make(이름="계열", 계정_번호=a, 버전=v)
        self.db.ok(f'UPDATE "{self.table}" SET "이름"=\'바뀐 계열\' WHERE "계정_번호"={a} AND "이름"=\'계열\'')
        self.assertEqual(self.db.val(f'SELECT string_agg("버전"::text, \',\' ORDER BY "버전") FROM "{self.table}" '
                                     f'WHERE "계정_번호"={a} AND "이름"=\'바뀐 계열\''), "1,2,3")

    def test_rename_cannot_collide_with_an_existing_lineage(self):
        a = self.account()
        r = self.make(이름="하나", 계정_번호=a)
        self.make(이름="둘", 계정_번호=a)
        self.db.fails(f'UPDATE "{self.table}" SET "이름"=\'둘\' WHERE "번호"={r}', f"uq_{self.table}_계정_이름_버전")

    # ---- 공개 여부 (0012) --------------------------------------------------
    def test_share_flag_defaults_to_false_for_owned_and_common_items(self):
        a = self.account()
        for owner in (a, None):
            r = self.make(계정_번호=owner)
            self.assertEqual(self.db.val(f'SELECT "공개여부" FROM "{self.table}" WHERE "번호"={r}'), "f")

    def test_share_flag_can_be_toggled_both_ways_and_per_version(self):
        a = self.account()
        v1 = self.make(이름="공유 후보", 계정_번호=a)
        v2 = self.make(이름="공유 후보", 계정_번호=a, 버전=2)
        self.db.ok(f'UPDATE "{self.table}" SET "공개여부"=TRUE WHERE "번호"={v1}')
        self.assertEqual(self.db.val(f'SELECT "공개여부" FROM "{self.table}" WHERE "번호" IN ({v1},{v2}) ORDER BY "번호"'),
                         "t\nf")
        self.db.ok(f'UPDATE "{self.table}" SET "공개여부"=FALSE WHERE "번호"={v1}')
        self.assertEqual(self.db.val(f'SELECT "공개여부" FROM "{self.table}" WHERE "번호"={v1}'), "f")

    def test_share_flag_change_cannot_carry_other_changes(self):
        r = self.make()
        self.update_fails(r, '"공개여부"=TRUE, "버전"=9')
        self.update_fails(r, f'"공개여부"=TRUE, "{self.content}"=\'{{"v": 9}}\'::jsonb')
        self.assertEqual(self.db.val(f'SELECT "공개여부" FROM "{self.table}" WHERE "번호"={r}'), "f")

    def test_share_flag_can_change_after_delete_mark_but_delete_stays_one_way(self):
        r = self.make()
        self.db.ok(f'UPDATE "{self.table}" SET "삭제일시"=CURRENT_TIMESTAMP, "공개여부"=TRUE WHERE "번호"={r}')
        self.db.ok(f'UPDATE "{self.table}" SET "공개여부"=FALSE WHERE "번호"={r}')
        self.update_fails(r, '"삭제일시"=NULL', "되돌릴 수 없습니다")

    # ---- 삭제 표시 ---------------------------------------------------------
    def test_delete_mark_is_allowed_once_and_keeps_the_row(self):
        r = self.make()
        self.db.ok(f'UPDATE "{self.table}" SET "삭제일시"=CURRENT_TIMESTAMP WHERE "번호"={r}')
        self.assertEqual(self.db.val(f'SELECT "삭제일시" IS NOT NULL FROM "{self.table}" WHERE "번호"={r}'), "t")

    def test_delete_mark_cannot_be_undone_or_changed(self):
        r = self.make()
        self.db.ok(f'UPDATE "{self.table}" SET "삭제일시"=CURRENT_TIMESTAMP WHERE "번호"={r}')
        self.update_fails(r, '"삭제일시"=NULL', "되돌릴 수 없습니다")
        self.update_fails(r, '"삭제일시"=CURRENT_TIMESTAMP + interval \'1 day\'', "되돌릴 수 없습니다")

    def test_delete_mark_cannot_be_combined_with_other_changes(self):
        r = self.make()
        self.update_fails(r, '"삭제일시"=CURRENT_TIMESTAMP, "버전"=9')
        self.assertEqual(self.db.val(f'SELECT "삭제일시" IS NULL FROM "{self.table}" WHERE "번호"={r}'), "t")

    def test_deleted_name_and_version_stay_reserved(self):
        a = self.account()
        r = self.make(이름="지울 것", 계정_번호=a)
        self.db.ok(f'UPDATE "{self.table}" SET "삭제일시"=CURRENT_TIMESTAMP WHERE "번호"={r}')
        self.ins_fails(self.table, f"uq_{self.table}_계정_이름_버전", 이름="지울 것", 계정_번호=a,
                       **{self.content: {}}, **self.other)
        self.make(이름="지울 것", 계정_번호=a, 버전=2)   # 새 버전은 가능

    def test_deleting_an_item_used_by_a_work_keeps_the_link(self):
        w = self.work()
        self.step(w, 1)
        r = self.make()
        if self.table == "진행단계":
            self.ins("진행구성", 작품_번호=w, 진행순서_순서=1, 진행단계_번호=r)
            link = '"진행구성" WHERE "진행단계_번호"'
        else:
            self.ins("기믹적용", 작품_번호=w, 순서=1, 기믹_번호=r, 진행순서_순서=1)
            link = '"기믹적용" WHERE "기믹_번호"'
        self.db.ok(f'UPDATE "{self.table}" SET "삭제일시"=CURRENT_TIMESTAMP WHERE "번호"={r}')
        self.assertEqual(self.db.val(f'SELECT count(*) FROM {link}={r}'), "1")
        # 물리 삭제는 여전히 참조 중이면 거부된다.
        self.db.fails(f'DELETE FROM "{self.table}" WHERE "번호"={r}', "foreign key constraint")


def _make_class(table: str, spec: dict):
    return type(
        f"TestLibrary_{table}",
        (LibraryVersionCases, Builders),
        {"table": table, "content": spec["content"], "other": spec["other"], "__test__": True},
    )


for _t, _s in TABLES.items():
    globals()[f"TestLibrary_{_t}"] = _make_class(_t, _s)


class TestCommonPhaseSeed(unittest.TestCase):
    """0015 가 넣은 시험용 공통 진행단계 11개를 0019 가 없앤다 (진행단계는 제작자가 직접 만든다)."""

    def make_db(self):
        name = "mm_seed_" + uuid.uuid4().hex[:12]
        admin_sql(f'CREATE DATABASE "{name}"')
        self.addCleanup(admin_sql, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        return name

    def test_new_database_has_no_phases_after_all_migrations(self):
        name = self.make_db()
        migrate.run(name, MIGRATIONS_DIR)
        self.assertEqual(Db(name).val('SELECT count(*) FROM "진행단계"'), "0")

    def test_seed_is_removed_but_referenced_rows_are_only_marked_deleted(self):
        name = self.make_db()
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        for p in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if p.name < "0019":
                (tmp / p.name).symlink_to(p)
        migrate.run(name, tmp)
        db = Db(name)
        self.assertEqual(db.val('SELECT count(*) FROM "진행단계"'), "11")
        acc = db.val("INSERT INTO \"계정\"(\"아이디\",\"패스워드\",\"닉네임\") VALUES ('a','x','a') RETURNING \"번호\"")
        w = db.val(f"INSERT INTO \"작품\"(\"계정_번호\",\"제목\",\"시놉시스\",\"장르\") VALUES ({acc},'t','s','g') RETURNING \"번호\"")
        used = db.val('SELECT "번호" FROM "진행단계" WHERE "이름" = \'조사\'')
        db.ok(f'INSERT INTO "진행순서"("작품_번호","순서") VALUES ({w},1)')
        db.ok(f'INSERT INTO "진행구성"("작품_번호","진행순서_순서","진행단계_번호") VALUES ({w},1,{used})')
        # 운영자가 직접 올린 공통 항목은 시험용 기본값이 아니므로 남는다
        db.ok("INSERT INTO \"진행단계\"(\"이름\",\"규칙\",\"설명\") VALUES ('운영자 단계','{}','d')")
        migrate.run(name, MIGRATIONS_DIR)
        rows = db.rows('SELECT "이름", "삭제일시" IS NOT NULL FROM "진행단계" ORDER BY "번호"')
        self.assertEqual(rows, [["조사", "t"], ["운영자 단계", "f"]])
        self.assertEqual(db.val('SELECT count(*) FROM "진행구성"'), "1")     # 연결은 그대로


class TestBackfillOfExistingRows(unittest.TestCase):
    """0011 이전에 같은 (계정, 이름) 행이 여러 개 있던 DB 도 0011 이 적용된다."""

    def setUp(self):
        self.dbname = "mm_lib_" + uuid.uuid4().hex[:12]
        admin_sql(f'CREATE DATABASE "{self.dbname}"')
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Db(self.dbname)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        admin_sql(f'DROP DATABASE IF EXISTS "{self.dbname}" WITH (FORCE)')

    def test_existing_duplicates_get_versions_in_number_order(self):
        for p in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if p.name < "0011":
                shutil.copy(p, self.tmp / p.name)
        migrate.run(self.dbname, self.tmp)

        self.db.ok("""INSERT INTO "계정"("아이디","패스워드","닉네임") VALUES ('u','h','n')""")
        for t, col in (("진행단계", '"규칙"'), ("기믹", '"조건"')):
            extra = ', \'d\'' if t == "진행단계" else ", '{}'"
            extra_col = ', "설명"' if t == "진행단계" else ', "결과"'
            for owner in ("NULL", "1"):
                for _ in range(3):
                    self.db.ok(f'INSERT INTO "{t}"("이름", {col}{extra_col}, "계정_번호") '
                               f"VALUES ('같은 이름', '{{}}'{extra}, {owner})")
            self.db.ok(f'INSERT INTO "{t}"("이름", {col}{extra_col}) VALUES (\'다른 이름\', \'{{}}\'{extra})')

        shutil.copy(next(MIGRATIONS_DIR.glob("0011_*.sql")), self.tmp)
        self.assertEqual(len(migrate.run(self.dbname, self.tmp)), 1)

        for t in ("진행단계", "기믹"):
            got = self.db.rows(
                f"""SELECT COALESCE("계정_번호"::text,'공통'), "이름", string_agg("버전"::text, ',' ORDER BY "번호")
                    FROM "{t}" GROUP BY 1, 2 ORDER BY COALESCE("계정_번호"::text,'공통') COLLATE "C", "이름" COLLATE "C" """)
            self.assertEqual(got, [["1", "같은 이름", "1,2,3"], ["공통", "같은 이름", "1,2,3"], ["공통", "다른 이름", "1"]])


if __name__ == "__main__":
    unittest.main()
