#!/usr/bin/env python3
"""적용된 DB 의 테이블 구조·제약조건·인덱스·트리거를 마크다운으로 출력한다. (표준 라이브러리 + psql)

사용법:
    python3 db/scripts/dump_schema_md.py --dbname murder_mystery > docs/SCHEMA_REFERENCE.md
"""
from __future__ import annotations

import argparse
import subprocess
import sys


def q(dbname: str, sql: str) -> list[list[str]]:
    p = subprocess.run(
        ["psql", "-X", "-q", "-A", "-t", "-F", "\x1f", "-v", "ON_ERROR_STOP=1", "-d", dbname, "-c", sql],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        sys.exit(p.stderr)
    return [line.split("\x1f") for line in p.stdout.splitlines() if line != ""]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dbname", required=True)
    dbname = ap.parse_args().dbname

    tables = [r[0] for r in q(dbname, """
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind='r' AND c.relname<>'schema_migrations'
        ORDER BY c.oid""")]

    print("# 스키마 참조 (자동 생성)\n")
    print("> `db/scripts/dump_schema_md.py` 가 마이그레이션이 적용된 실제 DB 에서 추출한 문서입니다. "
          "직접 수정하지 마세요.\n")
    print(f"테이블 {len(tables)}개 (생성 순서)\n")
    print("| 번호 | 테이블 |\n|---|---|")
    for i, t in enumerate(tables, 1):
        print(f"| {i} | {t} |")
    print()

    for t in tables:
        print(f"## {t}\n")
        print("| 순번 | 컬럼 | 타입 | NULL | 기본값 / 특성 |\n|---|---|---|---|---|")
        for r in q(dbname, f"""
            SELECT a.attnum, a.attname, format_type(a.atttypid, a.atttypmod),
                   CASE WHEN a.attnotnull THEN '불가' ELSE '가능' END,
                   CASE WHEN a.attidentity='a' THEN 'IDENTITY (GENERATED ALWAYS)'
                        WHEN a.attidentity='d' THEN 'IDENTITY (BY DEFAULT)'
                        ELSE COALESCE(pg_get_expr(d.adbin, d.adrelid), '') END
            FROM pg_attribute a
            LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
            WHERE a.attrelid='"{t}"'::regclass AND a.attnum>0 AND NOT a.attisdropped
            ORDER BY a.attnum"""):
            attnum, name, typ, null, dflt = r
            print(f"| {attnum} | {name} | {typ} | {null} | {dflt} |")
        print()

        cons = q(dbname, f"""
            SELECT c.contype, c.conname, pg_get_constraintdef(c.oid)
            FROM pg_constraint c WHERE c.conrelid='"{t}"'::regclass
            ORDER BY CASE c.contype WHEN 'p' THEN 1 WHEN 'u' THEN 2 WHEN 'f' THEN 3 ELSE 4 END, c.conname""")
        if cons:
            print("**제약조건**\n")
            print("| 종류 | 이름 | 정의 |\n|---|---|---|")
            kind = {"p": "PK", "u": "UNIQUE", "f": "FK", "c": "CHECK"}
            for typ, name, definition in cons:
                definition = definition.replace("|", "\\|")
                print(f"| {kind[typ]} | `{name}` | `{definition}` |")
            print()

        idx = q(dbname, f"""
            SELECT i.relname, pg_get_indexdef(i.oid)
            FROM pg_index x JOIN pg_class i ON i.oid=x.indexrelid
            WHERE x.indrelid='"{t}"'::regclass AND NOT x.indisprimary
              AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid=x.indexrelid AND c.contype IN ('u','p'))
            ORDER BY i.relname""")
        if idx:
            print("**추가 인덱스** (PK/UNIQUE 제약이 만드는 인덱스는 제외)\n")
            for name, definition in idx:
                print(f"- `{name}`: `{definition}`")
            print()

        trg = q(dbname, f"""
            SELECT tgname, pg_get_triggerdef(oid) FROM pg_trigger
            WHERE tgrelid='"{t}"'::regclass AND NOT tgisinternal ORDER BY tgname""")
        if trg:
            print("**트리거**\n")
            for name, definition in trg:
                print(f"- `{name}`: `{definition}`")
            print()


if __name__ == "__main__":
    main()
