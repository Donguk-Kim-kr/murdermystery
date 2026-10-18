"""작품 확정(스냅샷 만들기). docs/DB_RULES.md B9.

* 확정하면 그 시점의 제작 내용 전체가 `버전.시나리오`에 **그대로 복사**되어 이후 제작 화면에서 고쳐도 영향이 없다.
  제작용 테이블은 확정 뒤에도 계속 고칠 수 있고, 다시 확정하면 다음 버전("2.0", "3.0" …)이 생긴다.
* 제작 순서는 자유이므로 만드는 도중에는 아무것도 막지 않고, **확정할 때만** 검사한다.
  `errors`가 하나라도 있으면 확정할 수 없고, `warnings`는 알려 주기만 한다.
* 스냅샷 형식(`형식버전` 1): 최상위에 `작품`(기본정보), `인물`, 각 콘텐츠 테이블 이름 → 행 목록, `라이브러리`.
  행 목록의 각 행은 제작 시점의 `순서`를 그대로 가지며(다른 항목이 이 번호로 가리킨다), `번호`·`작품_번호`는 담지 않는다.
  `진행구성`·`기믹적용`이 가리키는 진행단계·기믹은 **내용 사본**을 `라이브러리`에 넣는다. 삭제된 항목은 뺀다.
* 사용 가능한 시각은 ISO 8601 글자로 저장한다. 미디어는 아직 지원하지 않아 담지 않는다.
"""
import json
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, status
from psycopg import Connection, sql
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import narrative
from .auth import CurrentUser
from .characters import COLUMNS as CHARACTER_COLUMNS
from .content import RESOURCES, Resource, card_display_names, columns, ensure_mine, key_col, phase_display_names
from .db import Conn
from .works import lock_work
from .josa import attach, quoted

FORMAT_VERSION = 1
router = APIRouter(prefix="/api/works/{work_id}", tags=["confirm"])

LIBRARY_COLUMNS = {
    "진행단계": ("번호", "계정_번호", "이름", "버전", "설명", "변경내역", "규칙"),
    "기믹": ("번호", "계정_번호", "이름", "버전", "설명", "변경내역", "조건", "결과"),
}
# 라이브러리를 가리키는 자원 -> (가리키는 칸, 라이브러리 테이블, 스냅샷의 라이브러리 키)
LIBRARY_LINKS = {"phase-steps": ("진행단계_번호", "진행단계"), "gimmick-uses": ("기믹_번호", "기믹")}


class VersionOut(BaseModel):
    번호: int
    버전: str
    생성일시: datetime
    변경사항: str | None


class ConfirmIn(BaseModel):
    변경사항: Annotated[str, Field(max_length=2000)] | None = None


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"JSON 으로 바꿀 수 없는 값: {type(value).__name__}")


def _dumps(value: Any) -> str:
    return json.dumps(value, default=_json_default, ensure_ascii=False)


def next_version(conn: Connection, work_id: int) -> str:
    """"N.0" 꼴. 버전 문자열은 사전순이 아니라 앞자리 숫자로 비교한다."""
    majors = []
    for row in conn.execute('SELECT "버전" FROM "버전" WHERE "작품_번호" = %s', (work_id,)).fetchall():
        head = row["버전"].split(".")[0]
        if head.isdigit():
            majors.append(int(head))
    return f"{max(majors, default=0) + 1}.0"


def _deleted_links(conn: Connection, res_key: str, work_id: int) -> list[dict]:
    """삭제된 라이브러리 항목을 가리키는 연결 (스냅샷에서 빠지고 경고로 알린다)."""
    col, table = LIBRARY_LINKS[res_key]
    res = next(r for r in RESOURCES if r.key == res_key)
    return conn.execute(
        sql.SQL(
            'SELECT u.{k} AS key, l."이름", l."버전", u."진행순서_순서" AS phase FROM {t} u '
            'JOIN {lib} l ON l."번호" = u.{col} WHERE u."작품_번호" = %s AND l."삭제일시" IS NOT NULL ORDER BY u.{k}'
        ).format(k=sql.Identifier(key_col(res)), t=sql.Identifier(res.table), lib=sql.Identifier(table),
                 col=sql.Identifier(col)),
        (work_id,),
    ).fetchall()


def check_work(conn: Connection, work_id: int) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    work = conn.execute(
        'SELECT "제목", "최소인원", "최대인원" FROM "작품" WHERE "번호" = %s', (work_id,)
    ).fetchone()
    chars = conn.execute(
        'SELECT "NPC", "범인" FROM "인물" WHERE "작품_번호" = %s', (work_id,)
    ).fetchall()
    players = [c for c in chars if not c["NPC"]]
    if not players:
        errors.append("플레이어가 맡을 인물이 없습니다. NPC가 아닌 인물을 하나 이상 만들어 주세요.")
    elif work["최소인원"] > work["최대인원"]:
        errors.append(f"최소 인원({work['최소인원']}명)이 플레이어 인물 수({work['최대인원']}명)보다 많습니다.")
    if not any(c["범인"] for c in chars):
        warnings.append("범인으로 표시된 인물이 없습니다.")
    count = lambda table: conn.execute(  # noqa: E731  (테이블 이름은 아래 고정 목록에서만 온다)
        sql.SQL('SELECT count(*) AS n FROM {t} WHERE "작품_번호" = %s').format(t=sql.Identifier(table)), (work_id,)
    ).fetchone()["n"]
    phases = conn.execute(
        'SELECT p."순서", (SELECT count(*) FROM "진행구성" s WHERE s."작품_번호" = p."작품_번호" AND s."진행순서_순서" = p."순서") AS n '
        'FROM "진행순서" p WHERE p."작품_번호" = %s ORDER BY p."순서"', (work_id,)
    ).fetchall()
    if not phases:
        errors.append("진행 순서(페이즈)가 없습니다. 페이즈를 하나 이상 만들어 주세요.")
    for p in phases:
        if p["n"] == 0:
            warnings.append(f"페이즈 {p['순서']}에 진행단계가 없습니다.")
    for table, text in (("엔딩분기", "엔딩 분기가 없습니다."), ("단서", "단서가 없습니다."), ("타임라인", "타임라인(사건의 진상)이 없습니다.")):
        if count(table) == 0:
            warnings.append(text)
    for key, word in (("phase-steps", "진행단계"), ("gimmick-uses", "기믹")):
        for row in _deleted_links(conn, key, work_id):
            warnings.append(
                f"페이즈 {row['phase']}에 연결된 {attach(f"{word} '{row['이름']}' v{row['버전']}", '은/는')} 삭제되어 확정 내용에서 빠집니다."
            )
    for combo in conn.execute(
        'SELECT c."이름" FROM "조합" c WHERE c."작품_번호" = %s AND NOT EXISTS '
        '(SELECT 1 FROM "조합재료" m WHERE m."작품_번호" = c."작품_번호" AND m."결과_조합_순서" = c."순서") ORDER BY c."순서"', (work_id,)
    ).fetchall():
        warnings.append(f"조합 '{combo['이름']}'에 재료가 없습니다.")
    errors.extend(script_errors(conn, work_id))
    errors.extend(condition_errors(conn, work_id))
    warnings.extend(story_selection_warnings(conn, work_id))
    warnings.extend(question_warnings(conn, work_id))
    return {"errors": errors, "warnings": warnings, "다음버전": next_version(conn, work_id)}


def condition_errors(conn: Connection, work_id: int) -> list[str]:
    """엔딩 분기와 후일담의 조건 식을 검사한다. 비어 있으면 항상 적용이고, 있으면 `{"식": "…"}` 모양이어야 하며 문법·이름이 맞아야 한다."""
    from .cards import condition_names
    from .script import ScriptError, compile_expression

    names = condition_names()
    found = []
    for table, label in (("엔딩분기", "엔딩 분기"), ("후일담", "후일담")):
        for row in conn.execute(
            sql.SQL('SELECT "순서", "조건", {name} AS "이름" FROM {t} WHERE "작품_번호" = %s ORDER BY "순서"').format(
                t=sql.Identifier(table), name=sql.SQL('"이름"') if table == "엔딩분기" else sql.SQL("NULL")
            ),
            (work_id,),
        ).fetchall():
            condition = row["조건"]
            who = f"{label} {row['이름'] or row['순서']}"
            if not condition:
                continue
            expression = condition.get("식") if isinstance(condition, dict) else None
            if not isinstance(expression, str) or not expression.strip():
                found.append(f"{who}의 조건은 {{\"식\": \"…\"}} 모양으로 써야 합니다.")
                continue
            try:
                compile_expression(expression, names)
            except ScriptError as err:
                found.append(f"{who}의 조건 식에 오류가 있습니다: {err}")
    return found


def story_selection_warnings(conn: Connection, work_id: int) -> list[str]:
    """프로필 숙지 카드가 고른 서사 번호가 인물의 서사 수를 넘으면 알린다(서사를 지우거나 줄여 번호가 밀린 경우)."""
    counts = {
        r["순서"]: (r["이름"], len(narrative.split(r["서사"])))
        for r in conn.execute('SELECT "순서", "이름", "서사" FROM "인물" WHERE "작품_번호" = %s', (work_id,)).fetchall()
    }
    found = []
    rows = conn.execute(
        'SELECT s."진행순서_순서" AS phase, l."이름" AS card, s."설정" FROM "진행구성" s JOIN "진행단계" l ON l."번호" = s."진행단계_번호" '
        'WHERE s."작품_번호" = %s AND s."설정" IS NOT NULL ORDER BY s."진행순서_순서", s."번호"', (work_id,)
    ).fetchall()
    for row in rows:
        picks = row["설정"].get("개인서사공개") if isinstance(row["설정"], dict) else None
        if not isinstance(picks, dict):
            continue
        for key, numbers in picks.items():
            if not (isinstance(key, str) and key.isdigit() and int(key) in counts and isinstance(numbers, list)):
                continue
            name, total = counts[int(key)]
            missing = sorted(n for n in numbers if isinstance(n, int) and n > total)
            if missing:
                nums = ", ".join(f"서사 {n}" for n in missing)
                found.append(f"페이즈 {row['phase']}의 {quoted(row['card'], '이/가')} 인물 '{name}'의 {attach(nums, '을/를')} 보여 주도록 했지만 그 서사가 없습니다(서사는 {total}개).")
    return found


def question_warnings(conn: Connection, work_id: int) -> list[str]:
    """개인 질문 카드에서 고르는 방식인데 선택지를 하나도 적지 않은 질문을 알린다(그 인물에게는 질문이 나오지 않는다)."""
    names = {r["순서"]: r["이름"] for r in conn.execute('SELECT "순서", "이름" FROM "인물" WHERE "작품_번호" = %s', (work_id,)).fetchall()}
    found = []
    rows = conn.execute(
        'SELECT s."진행순서_순서" AS phase, l."이름" AS card, s."설정" FROM "진행구성" s JOIN "진행단계" l ON l."번호" = s."진행단계_번호" '
        'WHERE s."작품_번호" = %s AND s."설정" IS NOT NULL ORDER BY s."진행순서_순서", s."번호"', (work_id,)
    ).fetchall()
    for row in rows:
        questions = row["설정"].get("질문") if isinstance(row["설정"], dict) else None
        if not isinstance(questions, dict):
            continue
        for key, definition in questions.items():
            if not (isinstance(definition, dict) and definition.get("방식") == "선택" and key.isdigit() and int(key) in names):
                continue
            if not [c for c in definition.get("선택") or [] if isinstance(c, str) and c.strip()]:
                found.append(f"페이즈 {row['phase']}의 {quoted(row['card'], '이/가')} 인물 '{names[int(key)]}'의 질문은 고르는 방식인데 선택지가 없어 질문이 나오지 않습니다.")
    return found


def script_errors(conn: Connection, work_id: int) -> list[str]:
    """이 작품의 페이즈에 놓인 진행단계의 스크립트를 검사한다(문법, 허용되지 않은 코드, 없는 이름). 같은 진행단계는 한 번만 본다."""
    from .cards import known_names
    from .script import ScriptError, compile_source

    rows = conn.execute(
        'SELECT DISTINCT l."번호", l."이름", l."버전", l."규칙" FROM "진행구성" s JOIN "진행단계" l ON l."번호" = s."진행단계_번호" '
        'WHERE s."작품_번호" = %s AND l."삭제일시" IS NULL ORDER BY l."번호"', (work_id,)
    ).fetchall()
    names = known_names()
    found = []
    for row in rows:
        rule = row["규칙"]
        source = rule.get("스크립트") if isinstance(rule, dict) else None
        if not isinstance(source, str) or not source.strip():
            continue
        try:
            compile_source(source, names)
        except ScriptError as err:
            found.append(f"진행단계 '{row['이름']}' v{row['버전']}의 스크립트에 오류가 있습니다: {err}")
    return found


def build_snapshot(conn: Connection, work_id: int) -> dict[str, Any]:
    work = conn.execute(
        'SELECT "제목", "시놉시스", "장르", "최소인원", "최대인원", "예상시간", "공통스토리" FROM "작품" WHERE "번호" = %s',
        (work_id,),
    ).fetchone()
    snap: dict[str, Any] = {"형식버전": FORMAT_VERSION, "작품": work}
    snap["인물"] = conn.execute(
        f'SELECT {CHARACTER_COLUMNS} FROM "인물" WHERE "작품_번호" = %s ORDER BY "순서"', (work_id,)
    ).fetchall()
    for person in snap["인물"]:
        # 확정할 때 해석한 서사 부분 목록(ID, 본문). 해석 규칙을 나중에 고쳐도 확정된 작품은 달라지지 않는다.
        person["서사_부분"] = [{"ID": p.id, "본문": p.text} for p in narrative.split(person["서사"])]
    used: dict[str, set[int]] = {"진행단계": set(), "기믹": set()}
    for res in RESOURCES:
        rows = _rows(conn, res, work_id)
        link = LIBRARY_LINKS.get(res.key)
        if link:
            col, table = link
            alive = {
                r["번호"] for r in conn.execute(
                    sql.SQL('SELECT "번호" FROM {t} WHERE "삭제일시" IS NULL').format(t=sql.Identifier(table))
                ).fetchall()
            }
            rows = [r for r in rows if r[col] in alive]
            used[table].update(r[col] for r in rows)
        if res.key == "phase-steps":    # 칸에 놓인 카드의 표시 이름(같은 카드가 둘 이상이면 1차·2차)도 확정 내용에 담는다
            names = {
                r["번호"]: r["이름"] for r in conn.execute('SELECT "번호", "이름" FROM "진행단계"').fetchall()
            }
            shown = card_display_names([{**r, "번호": i} for i, r in enumerate(rows)], names)
            rows = [{**r, "표시이름": shown[i]} for i, r in enumerate(rows)]
        snap[res.table] = rows
    # 페이즈 표시 이름(제작자가 정한 이름, 없으면 붙은 진행단계 이름을 이은 것)도 확정 내용에 담는다
    shown_phase = phase_display_names(snap["진행순서"], snap["진행구성"])
    snap["진행순서"] = [{**p, "표시이름": shown_phase[p["순서"]]} for p in snap["진행순서"]]
    snap["라이브러리"] = {
        table: [
            conn.execute(
                sql.SQL('SELECT {c} FROM {t} WHERE "번호" = %s').format(
                    c=sql.SQL(", ").join(sql.Identifier(c) for c in LIBRARY_COLUMNS[table]), t=sql.Identifier(table)
                ),
                (n,),
            ).fetchone()
            for n in sorted(ids)
        ]
        for table, ids in used.items()
    }
    return snap


def _rows(conn: Connection, res: Resource, work_id: int) -> list[dict]:
    cols = [c for c in columns(res) if c != "번호"]
    return conn.execute(
        sql.SQL('SELECT {cols} FROM {t} WHERE "작품_번호" = %s ORDER BY {k}').format(
            cols=sql.SQL(", ").join(sql.Identifier(c) for c in cols), t=sql.Identifier(res.table),
            k=sql.Identifier(key_col(res)),
        ),
        (work_id,),
    ).fetchall()


@router.get("/confirm/check")
def check(work_id: int, conn: Conn, me: CurrentUser) -> dict:
    ensure_mine(conn, work_id, me.계정.번호)
    return check_work(conn, work_id)


@router.post("/confirm", status_code=status.HTTP_201_CREATED, response_model=VersionOut)
def confirm(work_id: int, conn: Conn, me: CurrentUser, body: ConfirmIn = Body(default_factory=ConfirmIn)) -> dict:
    lock_work(conn, work_id, me.계정.번호)
    result = check_work(conn, work_id)
    if result["errors"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, " ".join(result["errors"]))
    version = result["다음버전"]
    snapshot = build_snapshot(conn, work_id)
    row = conn.execute(
        'INSERT INTO "버전" ("작품_번호", "버전", "시나리오", "변경사항") VALUES (%s, %s, %s, %s) '
        'RETURNING "번호", "버전", "생성일시", "변경사항"',
        (work_id, version, Jsonb(snapshot, dumps=_dumps), body.변경사항),
    ).fetchone()
    conn.execute('UPDATE "작품" SET "최신버전" = %s, "수정일시" = CURRENT_TIMESTAMP WHERE "번호" = %s', (version, work_id))
    return row


@router.get("/versions", response_model=list[VersionOut])
def versions(work_id: int, conn: Conn, me: CurrentUser) -> list[dict]:
    ensure_mine(conn, work_id, me.계정.번호)
    return conn.execute(
        'SELECT "번호", "버전", "생성일시", "변경사항" FROM "버전" WHERE "작품_번호" = %s ORDER BY "번호" DESC', (work_id,)
    ).fetchall()
