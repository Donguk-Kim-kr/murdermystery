"""기본(공통) 진행단계를 라이브러리에 등록한다. 공통 항목은 계정이 없고 모든 제작자가 고를 수 있다.

이미 같은 이름의 공통 항목이 있고 그 최신 버전의 스크립트가 같으면 건드리지 않는다. 내용이 다르면 새 버전으로 올리고
(라이브러리 항목은 고치지 않고 새 버전을 만든다), 없으면 1 버전으로 만든다. 여러 번 실행해도 같은 결과이다.
"""
from psycopg.types.json import Jsonb

from .default_phases import COMMON_PHASES


RENAMED = {"프롤로그": "공통 스토리"}   # 이름이 바뀐 기본 진행단계: 옛 이름의 모든 버전을 새 이름으로 바꾼다(이미 놓은 카드는 번호로 가리키므로 그대로 이어진다)


def register(conn) -> list[str]:
    """등록한 일을 글로 돌려준다(예: "조사: 새로 만듦 v1")."""
    done: list[str] = []
    for old, new in RENAMED.items():
        has = lambda name: conn.execute(  # noqa: E731
            'SELECT 1 FROM "진행단계" WHERE "계정_번호" IS NULL AND "이름" = %s LIMIT 1', (name,)).fetchone() is not None
        if has(old) and not has(new):
            conn.execute('UPDATE "진행단계" SET "이름" = %s WHERE "계정_번호" IS NULL AND "이름" = %s', (new, old))
            done.append(f"{old}: 이름을 {new}(으)로 바꿈")
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
