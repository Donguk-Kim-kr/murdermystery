"""엑셀 명세서 ↔ 실제 DB 카탈로그 대조 테스트 (요구사항 2, 3, 9).

명세서(db/spec/schema_spec.xlsx)를 직접 읽어 다음을 검증한다.
  * 컬럼 이름/순서/데이터타입/NULL 허용/기본값/IDENTITY
  * 기본키, 단일·복합 외래키, 단일·복합 UNIQUE, CHECK 개수
  * 명세서에 없는 FK/UNIQUE/PK 가 DB 에 없는지 (반대 방향)
  * 모든 FK 의 컬럼 타입 일치, FK 대상 테이블이 컬럼 이름 규칙과 일치
  * 모든 FK 에 이를 지원하는 인덱스가 있는지
"""
from __future__ import annotations

import re
import unittest
from collections import defaultdict

import openpyxl

from helpers import SPEC_PATH, PgTestCase

TYPE_MAP = {
    "INTEGER": "integer",
    "TEXT": "text",
    "TIMESTAMPTZ": "timestamp with time zone",
    "TIMESTAMP": "timestamp without time zone",
    "BOOLEAN": "boolean",
    "JSONB": "jsonb",
}

CHECK_RE = re.compile(r"CHECK\s*\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)")


def s(v) -> str:
    return "" if v is None else str(v).strip()


def load_spec() -> dict[str, list[dict]]:
    wb = openpyxl.load_workbook(SPEC_PATH, data_only=True)
    spec: dict[str, list[dict]] = {}
    for ws in wb.worksheets:
        if ws.title == "목차":
            continue
        # 시트에는 빈 행이 섞여 있을 수 있으므로 완전히 빈 행은 건너뛴다.
        rows = [r for r in ws.iter_rows(values_only=True) if any(c is not None for c in r)]
        assert s(rows[0][0]) == "테이블명" and s(rows[0][1]) == ws.title, ws.title
        assert [s(x) for x in rows[2][:8]] == [
            "순번", "컬럼명", "컬럼 설명", "데이터타입", "Null허용", "기본값", "특징", "제약조건"
        ], ws.title
        cols = []
        for r in rows[3:]:
            if r[0] is None:
                continue
            cols.append(dict(
                name=s(r[1]), type=s(r[3]), nullable=s(r[4]),
                default=r[5], feature=s(r[6]), constraint=s(r[7]),
            ))
        spec[ws.title] = cols
    return spec


def expected_default(col: dict):
    """(kind, value): kind ∈ identity | none | now | literal"""
    d = col["default"]
    ds = s(d)
    if ds == "자동생성":
        return ("identity", None)
    if ds == "없음" or ds == "":
        return ("none", None)
    if ds == "CURRENT_TIMESTAMP":
        return ("now", None)
    t = col["type"]
    if t == "BOOLEAN":
        return ("literal", ds.lower())
    if t == "INTEGER":
        return ("literal", str(int(float(ds))))
    if t == "TEXT":
        return ("literal", "'" + ds.strip("'") + "'::text")
    raise AssertionError(f"처리하지 못한 기본값: {col}")


def parse_constraints(cols: list[dict]):
    pk, fk_single, fk_comp, uq_single, uq_comp, checks = set(), set(), set(), set(), set(), set()
    for c in cols:
        text = c["constraint"]
        if text in ("", "없음"):
            continue
        if "기본키(PK)" in text:
            pk.add(c["name"])
        for m in re.findall(r"복합 외래키\(([^)]*)\)", text):
            fk_comp.add(tuple(x.strip() for x in m.split(",")))
        if re.search(r"(?<!복합 )외래키\(FK\)", text):
            fk_single.add(c["name"])
        for m in re.findall(r"복합 UNIQUE\s*\(([^)]*)\)", text):
            uq_comp.add(tuple(x.strip() for x in m.split(",")))
        if re.search(r"(?<!복합 )UNIQUE(?!\s*\()", text):
            uq_single.add(c["name"])
        for m in CHECK_RE.findall(text):
            checks.add(re.sub(r"\s+", " ", m))
    return pk, fk_single, fk_comp, uq_single, uq_comp, checks


class TestSpecConformance(PgTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.spec = load_spec()
        db = cls.db
        cls.cols = defaultdict(dict)  # table -> name -> dict
        cls.col_order = defaultdict(list)
        for r in db.rows(
            """SELECT table_name, column_name, data_type, is_nullable, COALESCE(column_default,''),
                      is_identity, COALESCE(identity_generation,'')
               FROM information_schema.columns
               WHERE table_schema='public' AND table_name<>'schema_migrations'
               ORDER BY table_name, ordinal_position"""
        ):
            t, c, dt, nul, dflt, ident, gen = r
            cls.cols[t][c] = dict(type=dt, nullable=nul, default=dflt, identity=ident, gen=gen)
            cls.col_order[t].append(c)

        cls.cons = defaultdict(list)  # table -> list of (contype, name, cols, ftable, fcols, deltype)
        for r in db.rows(
            """SELECT cl.relname, c.contype, c.conname,
                      COALESCE((SELECT string_agg(a.attname, ',' ORDER BY k.ord)
                                FROM unnest(c.conkey) WITH ORDINALITY k(attnum, ord)
                                JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.attnum),''),
                      COALESCE(fcl.relname,''),
                      COALESCE((SELECT string_agg(a.attname, ',' ORDER BY k.ord)
                                FROM unnest(c.confkey) WITH ORDINALITY k(attnum, ord)
                                JOIN pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=k.attnum),''),
                      c.confdeltype
               FROM pg_constraint c
               JOIN pg_class cl ON cl.oid=c.conrelid
               JOIN pg_namespace n ON n.oid=cl.relnamespace
               LEFT JOIN pg_class fcl ON fcl.oid=c.confrelid
               WHERE n.nspname='public' AND cl.relname<>'schema_migrations'"""
        ):
            t, typ, name, colsx, ft, fcols, dt = r
            cls.cons[t].append((typ, name, tuple(colsx.split(",")) if colsx else (), ft,
                                tuple(fcols.split(",")) if fcols else (), dt))

        cls.indexes = defaultdict(list)  # table -> list of column tuples (idx key columns, in order)
        for r in db.rows(
            """SELECT t.relname,
                      (SELECT string_agg(a.attname, ',' ORDER BY k.ord)
                       FROM unnest(i.indkey::int2[]) WITH ORDINALITY k(attnum, ord)
                       JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=k.attnum)
               FROM pg_index i
               JOIN pg_class t ON t.oid=i.indrelid
               JOIN pg_namespace n ON n.oid=t.relnamespace
               WHERE n.nspname='public' AND t.relname<>'schema_migrations' AND i.indisvalid"""
        ):
            if r[1]:
                cls.indexes[r[0]].append(tuple(r[1].split(",")))

    # ---------------------------------------------------------------- 컬럼
    def test_columns_match_spec(self):
        problems = []
        for table, scols in self.spec.items():
            self.assertIn(table, self.cols, f"테이블 없음: {table}")
            actual_names = self.col_order[table]
            spec_names = [c["name"] for c in scols]
            if actual_names != spec_names:
                problems.append(f"{table}: 컬럼 이름/순서 불일치\n  명세서={spec_names}\n  실제  ={actual_names}")
                continue
            for c in scols:
                a = self.cols[table][c["name"]]
                exp_type = TYPE_MAP[c["type"]]
                if a["type"] != exp_type:
                    problems.append(f"{table}.{c['name']}: 타입 {a['type']} != {exp_type}")
                exp_null = {"불가": "NO", "가능": "YES"}[c["nullable"]]
                if a["nullable"] != exp_null:
                    problems.append(f"{table}.{c['name']}: NULL허용 {a['nullable']} != {exp_null}")
                kind, val = expected_default(c)
                if kind == "identity":
                    if a["identity"] != "YES" or a["gen"] != "ALWAYS" or a["default"]:
                        problems.append(f"{table}.{c['name']}: IDENTITY(ALWAYS) 아님: {a}")
                else:
                    if a["identity"] == "YES":
                        problems.append(f"{table}.{c['name']}: 명세서에 없는 IDENTITY")
                    if kind == "none" and a["default"]:
                        problems.append(f"{table}.{c['name']}: 기본값 없어야 하는데 {a['default']!r}")
                    elif kind == "now" and "CURRENT_TIMESTAMP" not in a["default"]:
                        problems.append(f"{table}.{c['name']}: 기본값 CURRENT_TIMESTAMP 아님: {a['default']!r}")
                    elif kind == "literal" and a["default"] != val:
                        problems.append(f"{table}.{c['name']}: 기본값 {a['default']!r} != {val!r}")
        self.assertEqual(problems, [], "\n".join(problems))

    def test_primary_key_is_number_identity_integer_everywhere(self):
        for table in self.spec:
            pks = [c for c in self.cons[table] if c[0] == "p"]
            self.assertEqual(len(pks), 1, table)
            self.assertEqual(pks[0][2], ("번호",), table)
            self.assertEqual(self.cols[table]["번호"]["type"], "integer", table)
            self.assertEqual(self.cols[table]["번호"]["identity"], "YES", table)

    # ------------------------------------------------------------ 제약조건
    def test_constraints_match_spec_both_directions(self):
        problems = []
        for table, scols in self.spec.items():
            pk, fk_single, fk_comp, uq_single, uq_comp, checks = parse_constraints(scols)
            act = self.cons[table]
            act_fk_single = {c[2][0] for c in act if c[0] == "f" and len(c[2]) == 1}
            act_fk_comp = {c[2] for c in act if c[0] == "f" and len(c[2]) > 1}
            act_uq_single = {c[2][0] for c in act if c[0] == "u" and len(c[2]) == 1}
            act_uq_comp = {c[2] for c in act if c[0] == "u" and len(c[2]) > 1}
            act_pk = {c[2][0] for c in act if c[0] == "p"}
            act_checks = [c for c in act if c[0] == "c"]

            for label, exp, got in [
                ("PK", pk, act_pk),
                ("단일 FK", fk_single, act_fk_single),
                ("복합 FK", fk_comp, act_fk_comp),
                ("단일 UNIQUE", uq_single, act_uq_single),
                ("복합 UNIQUE", uq_comp, act_uq_comp),
            ]:
                if exp != got:
                    problems.append(f"{table}: {label} 불일치 명세서-only={sorted(exp - got)} DB-only={sorted(got - exp)}")
            if len(checks) != len(act_checks):
                problems.append(
                    f"{table}: CHECK 개수 명세서={len(checks)} DB={len(act_checks)}\n"
                    f"   명세서={sorted(checks)}\n   DB={[c[1] for c in act_checks]}")
        self.assertEqual(problems, [], "\n".join(problems))

    # ------------------------------------------------- FK 타입 / 대상 / 인덱스
    def _fks(self):
        for table, lst in self.cons.items():
            for typ, name, cols, ft, fcols, dt in lst:
                if typ == "f":
                    yield table, name, cols, ft, fcols, dt

    def test_fk_column_types_equal_referenced_types(self):
        problems = []
        for table, name, cols, ft, fcols, _ in self._fks():
            for c, fc in zip(cols, fcols):
                a, b = self.cols[table][c]["type"], self.cols[ft][fc]["type"]
                if a != b:
                    problems.append(f"{name}: {table}.{c}({a}) != {ft}.{fc}({b})")
        self.assertEqual(problems, [], "\n".join(problems))
        self.assertGreater(len(list(self._fks())), 50)

    def test_fk_targets_follow_column_naming(self):
        """FK 컬럼 이름에서 유추한 대상 테이블과 실제 대상이 같아야 한다."""
        def target(cols: tuple[str, ...]) -> str:
            col = [c for c in cols if c != "작품_번호"] or ["작품_번호"]
            name = col[0]
            for p in ("상위_", "대상_", "결과_"):
                if name.startswith(p):
                    name = name[len(p):]
            return re.sub(r"_(순서|번호|버전)$", "", name)

        problems = []
        for table, name, cols, ft, fcols, _ in self._fks():
            if target(cols) != ft:
                problems.append(f"{name}: {table}{cols} → {ft} (기대 {target(cols)})")
        self.assertEqual(problems, [], "\n".join(problems))

    def test_composite_fk_targets_are_unique_keys(self):
        """복합 FK 가 참조하는 컬럼 조합은 대상 테이블의 PK/UNIQUE 와 정확히 일치해야 한다 (요구사항 9)."""
        problems = []
        for table, name, cols, ft, fcols, _ in self._fks():
            keys = {c[2] for c in self.cons[ft] if c[0] in ("p", "u")}
            if fcols not in keys:
                problems.append(f"{name}: 참조 대상 {ft}{fcols} 는 PK/UNIQUE 가 아님")
        self.assertEqual(problems, [], "\n".join(problems))

    def test_every_fk_has_supporting_index(self):
        problems = []
        for table, name, cols, ft, fcols, _ in self._fks():
            n = len(cols)
            ok = any(set(idx[:n]) == set(cols) and len(idx) >= n for idx in self.indexes[table])
            if not ok:
                problems.append(f"{name}: {table}{cols} 를 앞쪽 컬럼으로 갖는 인덱스가 없음")
        self.assertEqual(problems, [], "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
