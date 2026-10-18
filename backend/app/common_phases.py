"""기본(공통) 진행단계를 라이브러리에 등록한다. 공통 항목은 계정이 없고 모든 제작자가 고를 수 있다.

이미 같은 이름의 공통 항목이 있고 그 최신 버전의 스크립트가 같으면 건드리지 않는다. 내용이 다르면 새 버전으로 올리고
(라이브러리 항목은 고치지 않고 새 버전을 만든다), 없으면 1 버전으로 만든다. 여러 번 실행해도 같은 결과이다.
"""
from psycopg.types.json import Jsonb

from .default_phases import COMMON_PHASES
from .josa import attach


RENAMED = {"프롤로그": "공통 스토리"}   # 이름이 바뀐 기본 진행단계: 옛 이름의 모든 버전을 새 이름으로 바꾼다(이미 놓은 카드는 번호로 가리키므로 그대로 이어진다)


def register(conn) -> list[str]:
    """등록한 일을 글로 돌려준다(예: "조사: 새로 만듦 v1")."""
    done: list[str] = []
    for old, new in RENAMED.items():
        has = lambda name: conn.execute(  # noqa: E731
            'SELECT 1 FROM "진행단계" WHERE "계정_번호" IS NULL AND "이름" = %s LIMIT 1', (name,)).fetchone() is not None
        if has(old) and not has(new):
            conn.execute('UPDATE "진행단계" SET "이름" = %s WHERE "계정_번호" IS NULL AND "이름" = %s', (new, old))
            done.append(f"{old}: 이름을 {attach(new, '으로/로')} 바꿈")
    for name, description, source, _settings in COMMON_PHASES:
        rule = {"스크립트": source}
        latest = conn.execute(
            'SELECT "버전", "규칙", "설명" FROM "진행단계" WHERE "계정_번호" IS NULL AND "이름" = %s AND "삭제일시" IS NULL '
            'ORDER BY "버전" DESC LIMIT 1',
            (name,),
        ).fetchone()
        if latest is not None and latest[1] == rule and latest[2] == description:
            continue
        last = conn.execute(
            'SELECT COALESCE(MAX("버전"), 0) FROM "진행단계" WHERE "계정_번호" IS NULL AND "이름" = %s', (name,)
        ).fetchone()[0]
        conn.execute(
            'INSERT INTO "진행단계" ("계정_번호", "이름", "설명", "버전", "변경내역", "규칙") VALUES (NULL, %s, %s, %s, %s, %s)',
            (name, description, last + 1, "기본 진행단계 등록" if last == 0 else "기본 진행단계 스크립트 갱신", Jsonb(rule)),
        )
        done.append(f"{name}: {'새로 만듦' if last == 0 else '새 버전'} v{last + 1}")
    return done


def reset_to_v1(conn) -> list[str]:
    """공통 진행단계마다 가장 최신 내용만 남기고 나머지 버전을 모두 지운 뒤, 그 내용을 v1 로 다시 만든다.

    라이브러리 항목은 수정할 수 없고(버전도 못 바꾼다) 작품의 카드(`진행구성`)가 번호로 가리키므로, 옛 행의 이름을 잠깐 바꿔 두고
    새 v1 행을 만든 다음 카드를 새 행으로 옮기고 옛 행을 지운다. 이미 놓은 카드는 그대로 이어진다(같은 단계의 서로 다른 버전이 한 페이즈에
    함께 놓여 있었다면 하나만 남는다). 확정된 버전은 진행단계 내용을 사본으로 갖고 있어 영향이 없다. 이미 v1 하나뿐인 항목은 건드리지 않는다.
    """
    done: list[str] = []
    names = [r[0] for r in conn.execute('SELECT DISTINCT "이름" FROM "진행단계" WHERE "계정_번호" IS NULL ORDER BY "이름"').fetchall()]
    for name in names:
        rows = conn.execute(
            'SELECT "번호", "버전", "설명", "규칙", "공개여부", "삭제일시" FROM "진행단계" WHERE "계정_번호" IS NULL AND "이름" = %s '
            'ORDER BY "버전" DESC', (name,)).fetchall()
        live = [r for r in rows if r[5] is None]
        if not live or (len(rows) == 1 and rows[0][1] == 1):
            continue
        latest = live[0]
        old_ids = [r[0] for r in rows]
        with conn.transaction():
            conn.execute('UPDATE "진행단계" SET "이름" = %s WHERE "번호" = ANY(%s)', (f"{name} (정리 전)", old_ids))
            new_id = conn.execute(
                'INSERT INTO "진행단계" ("계정_번호", "이름", "설명", "버전", "변경내역", "규칙", "공개여부") '
                'VALUES (NULL, %s, %s, 1, %s, %s, %s) RETURNING "번호"',
                (name, latest[2], "기본 진행단계 정리(최신 내용을 v1 로 다시 만듦)", Jsonb(latest[3]), latest[4]),
            ).fetchone()[0]
            conn.execute(
                'DELETE FROM "진행구성" a USING "진행구성" b WHERE a."진행단계_번호" = ANY(%s) AND b."진행단계_번호" = ANY(%s) '
                'AND a."작품_번호" = b."작품_번호" AND a."진행순서_순서" = b."진행순서_순서" AND a."번호" > b."번호"', (old_ids, old_ids))
            moved = conn.execute('UPDATE "진행구성" SET "진행단계_번호" = %s WHERE "진행단계_번호" = ANY(%s)', (new_id, old_ids)).rowcount
            conn.execute('DELETE FROM "진행단계" WHERE "번호" = ANY(%s)', (old_ids,))
        done.append(f"{name}: 버전 {len(rows)}개 → v1 (놓인 카드 {moved}개 이어 붙임)")
    return done
