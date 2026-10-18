"""작품 제작용 콘텐츠 API (장소, 단서, 증언, 조합, 사건, 타임라인, 엔딩분기, 후일담, 관계, 투표, 자료, 진행).

* 모든 콘텐츠 테이블이 같은 규칙(작품 안에서 `순서` 번호 또는 `번호`로 식별, 소유자만 접근)을 따르므로,
  테이블마다 따로 쓰지 않고 `RESOURCES` 명세 하나에서 API 와 화면 입력 양식을 함께 만든다.
* 제작 순서는 자유여야 하므로(docs/ENGINE_DESIGN.md 1-7) 어떤 것부터 채워도 되고, 다른 항목을 가리키는 칸은 대부분 비워 둘 수 있다.
  완성도 검증은 만드는 도중이 아니라 확정할 때 한다 (`confirm.py`).
* 식별자(테이블·컬럼 이름)는 이 파일의 명세에서만 가져오므로 SQL 에 끼워 넣어도 안전하다.
* 규칙 형식(JSON)은 아직 정해지지 않아 `json` 종류는 객체(딕셔너리)이기만 하면 받는다.
"""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, HTTPException, status
from psycopg import Connection, errors, sql
from psycopg.types.json import Jsonb

from . import narrative
from .auth import CurrentUser
from .db import Conn
from .ordering import next_order
from .works import lock_work, not_found

NAME_HELP = "나중에 바꿀 수 있습니다"


@dataclass(frozen=True)
class F:
    """콘텐츠 테이블의 입력 칸 하나."""

    name: str
    kind: str  # text | long | int | bool | json | ref | libref | ts
    required: bool = False
    max: int | None = None
    min: int | None = None
    ref: str | None = None  # kind == "ref" 일 때 가리키는 자원의 키 (같은 작품 안의 `순서`)
    label: str | None = None
    help: str | None = None
    default: Any = None


@dataclass(frozen=True)
class Resource:
    key: str
    table: str
    label: str
    fields: tuple[F, ...]
    ordered: bool = True  # True: (작품_번호, 순서) 로 식별 / False: 번호 로 식별
    title: tuple[str, ...] = ()  # 목록에서 제목처럼 보여 줄 칸 (앞에서부터 처음 값이 있는 것)
    group_by: str | None = None  # 이 칸이 같은 항목끼리 묶어 보여 준다
    help: str | None = None
    hidden: bool = False  # True: 화면에 따로 보이지 않는다(다른 항목의 입력 화면에 합쳐져 있다). API·스냅샷에는 그대로 있다
    has_parts: bool = False  # True: 조합처럼 재료 목록(`재료`)을 함께 입력받는다


def _ref(name: str, ref: str, label: str | None = None, required: bool = False) -> F:
    return F(name, "ref", required=required, ref=ref, label=label)


RESOURCES: tuple[Resource, ...] = (
    Resource("places", "장소", "장소", (
        _ref("상위_장소_순서", "places", "상위 장소"),
        F("이름", "text", True, 100, help=NAME_HELP),
        F("유형", "text", max=50),
        F("특징", "long", max=5000, label="특징·설명"),
    ), title=("이름",)),
    Resource("clues", "단서", "단서", (
        F("이름", "text", True, 100, help=NAME_HELP),
        F("공개이름", "text", max=100, help="남들에게 보여 주는 이름입니다(예: A의 서랍). 이름은 진짜 이름입니다. 비워 두어도 됩니다"),
        F("내용", "long", max=5000),
        F("기능", "long", max=2000),
        _ref("인물_순서", "characters", "관련 인물"),
        _ref("장소_순서", "places", "관련 장소"),
    ), title=("이름",)),
    Resource("testimonies", "증언", "증언", (
        F("이름", "text", True, 100, help="진짜 이름입니다(예: A의 마약소문). "+NAME_HELP),
        F("공개이름", "text", max=100, help="남들에게 보여 주는 이름입니다(예: 지나가던 사람). 비워 두어도 됩니다"),
        F("내용", "long", True, 5000),
        _ref("인물_순서", "characters", "관련 인물"),
        _ref("장소_순서", "places", "관련 장소"),
    ), title=("이름", "내용")),
    Resource("combos", "조합", "조합", (
        F("이름", "text", True, 100, help=NAME_HELP),
        F("공개이름", "text", max=100, help="남들에게 보여 주는 이름입니다(예: A의 서랍). 이름은 진짜 이름입니다. 비워 두어도 됩니다"),
        F("내용", "long", max=5000),
        F("기능", "long", max=2000),
    ), title=("이름",), has_parts=True,
        help="재료는 단서·증언·조합에서 골라 넣습니다. 같은 재료를 두 번 넣어도 한 번만 쓰입니다."),
    Resource("combo-parts", "조합재료", "조합 재료", (
        _ref("결과_조합_순서", "combos", "만들어지는 조합", required=True),
        _ref("단서_순서", "clues", "재료: 단서"),
        _ref("증언_순서", "testimonies", "재료: 증언"),
        _ref("조합_순서", "combos", "재료: 조합"),
    ), ordered=False, group_by="결과_조합_순서", hidden=True,
        help="재료는 단서·증언·조합 중 정확히 하나를 고릅니다."),
    Resource("incidents", "사건", "사건", (
        F("설명", "long", max=5000),
    ), title=("설명",)),
    Resource("incident-details", "사건설명", "사건 상세", (
        _ref("사건_순서", "incidents", "사건", required=True),
        _ref("인물_순서", "characters", "피해자"),
        F("상태", "text", max=50),
        F("설명", "long", max=5000),
        F("추정발생시간", "ts"),
        F("추정종료시간", "ts"),
    ), ordered=False, group_by="사건_순서"),
    Resource("timelines", "타임라인", "타임라인(사건의 진상)", (
        F("시작시간", "ts"),
        F("종료시간", "ts"),
        F("설명", "long", True, 5000),
    ), title=("설명",)),
    Resource("endings", "엔딩분기", "엔딩 분기", (
        F("이름", "text", True, 100, help=NAME_HELP),
        F("조건", "json", True, default={}, help="엔딩이 나오는 조건. {\"식\": \"조건 식\"} 으로 씁니다(예: {\"식\": \"결과_인물('최종 투표') is not None\"}). 비워 두면({}) 항상 나옵니다. 조건이 맞는 엔딩은 모두 순서대로 보입니다."),
        F("내용", "long", True, 5000),
    ), title=("이름", "내용")),
    Resource("epilogues", "후일담", "후일담", (
        _ref("인물_순서", "characters", "대상 인물 (비우면 전체)"),
        F("조건", "json", default=None, help="비워 두면 항상 적용됩니다. {\"식\": \"조건 식\"} 으로 씁니다. 조건이 맞는 후일담은 모두 순서대로 보입니다."),
        F("내용", "long", True, 5000),
    ), title=("내용",)),
    Resource("relations", "관계", "관계", (
        _ref("인물_순서", "characters", "인물", required=True),
        _ref("대상_인물_순서", "characters", "상대 인물", required=True),
        F("관계", "text", True, 200),
    ), ordered=False, group_by="인물_순서"),
    Resource("votes", "투표", "투표", (
        _ref("진행순서_순서", "phases", "진행되는 페이즈", required=True),
        F("이름", "text", True, 100, help=NAME_HELP),
        F("내용", "long", True, 5000),
        F("규칙", "json", True, default={}, help="규칙 형식이 정해지기 전이라 JSON 객체를 직접 씁니다."),
    ), title=("이름",)),
    Resource("materials", "자료", "자료(기믹이 불러 쓰는 글)", (
        F("제목", "text", True, 200, help=NAME_HELP),
        F("내용", "long", True, 20000),
    ), title=("제목",)),
    Resource("phases", "진행순서", "페이즈(진행 순서)", (
        F("이름", "text", max=100, label="페이즈 이름", help="플레이어에게 보이는 이름입니다. 비우면 안의 진행단계 이름으로 보입니다"),
        F("진행시간", "int", True, min=0, max=1440, default=30, label="진행 시간(분)"),
    ), title=("이름",),
        help="페이즈 위치는 끼워 넣기·옮기기로 바꿉니다. (칸 번호는 다른 항목이 가리키므로 그대로 두고 칸의 내용을 옮깁니다)"),
    Resource("phase-steps", "진행구성", "페이즈의 진행단계", (
        _ref("진행순서_순서", "phases", "페이즈", required=True),
        F("진행단계_번호", "libref", True, ref="phases", label="진행단계"),
        F("설정", "json", label="세부 설정", help="이 페이즈에서만 정의의 기본값을 덮어쓰는 설정입니다. 비우면 정의의 기본값을 씁니다"),
    ), ordered=False, group_by="진행순서_순서"),
    Resource("gimmick-uses", "기믹적용", "페이즈에 붙은 기믹", (
        F("기믹_번호", "libref", True, ref="gimmicks", label="기믹"),
        _ref("진행순서_순서", "phases", "적용되는 페이즈", required=True),
        F("설정", "json", label="세부 설정", help="이 페이즈에서만 정의의 기본값을 덮어쓰는 설정입니다. 비우면 정의의 기본값을 씁니다"),
    ), group_by="진행순서_순서"),
)
BY_KEY = {r.key: r for r in RESOURCES}
# 라이브러리 항목을 가리키는 칸 -> 라이브러리 테이블
LIBRARY_TABLE = {"phase-steps": "진행단계", "gimmick-uses": "기믹"}

# 화면의 참조 선택지를 위해 함께 내려 주는 인물(관리는 characters.py)
CHARACTER_PSEUDO = {"key": "characters", "label": "인물", "key_col": "순서", "title_fields": ["이름"], "external": True}

schema_router = APIRouter(prefix="/api/content", tags=["content"])
router = APIRouter(prefix="/api/works/{work_id}/content", tags=["content"])


def key_col(res: Resource) -> str:
    return "순서" if res.ordered else "번호"


def columns(res: Resource) -> list[str]:
    return [key_col(res), *[f.name for f in res.fields]]


def field_meta(f: F) -> dict:
    return {
        "name": f.name, "kind": f.kind, "required": f.required, "max": f.max, "min": f.min,
        "ref": f.ref, "label": f.label or f.name, "help": f.help, "default": f.default,
    }


@schema_router.get("/schema")
def content_schema(me: CurrentUser) -> dict:
    """화면이 입력 양식을 그리는 데 쓰는 명세."""
    return {
        "resources": [
            {
                "key": r.key, "label": r.label, "key_col": key_col(r), "title_fields": list(r.title),
                "group_by": r.group_by, "help": r.help, "hidden": r.hidden, "has_parts": r.has_parts, "fields": [field_meta(f) for f in r.fields],
            }
            for r in RESOURCES
        ],
        "external": [CHARACTER_PSEUDO],
    }


def _invalid(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def clean_value(f: F, value: Any) -> Any:
    label = f.label or f.name
    if value is None or (isinstance(value, str) and f.kind in ("text", "long") and value.strip() == ""):
        if f.required:
            raise _invalid(f"{label}: 비울 수 없는 항목입니다")
        return None
    if f.kind in ("text", "long"):
        if not isinstance(value, str):
            raise _invalid(f"{label}: 글자로 입력해 주세요")
        if f.max is not None and len(value) > f.max:
            raise _invalid(f"{label}: {f.max}자를 넘을 수 없습니다")
        return value
    if f.kind in ("int", "ref", "libref"):
        if isinstance(value, bool) or not isinstance(value, int):
            raise _invalid(f"{label}: 숫자로 입력해 주세요")
        lo = f.min if f.min is not None else (1 if f.kind in ("ref", "libref") else None)
        if lo is not None and value < lo:
            raise _invalid(f"{label}: {lo} 이상이어야 합니다")
        if f.max is not None and value > f.max:
            raise _invalid(f"{label}: {f.max} 이하여야 합니다")
        return value
    if f.kind == "bool":
        if not isinstance(value, bool):
            raise _invalid(f"{label}: 켜짐/꺼짐으로 입력해 주세요")
        return value
    if f.kind == "json":
        if not isinstance(value, dict):
            raise _invalid(f"{label}: JSON 객체({{...}})로 입력해 주세요")
        return Jsonb(value)
    if f.kind == "ts":
        if not isinstance(value, str):
            raise _invalid(f"{label}: 날짜와 시각을 입력해 주세요")
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            raise _invalid(f"{label}: 날짜와 시각 형식이 맞지 않습니다") from None
    raise AssertionError(f.kind)  # 명세 오류


def clean_body(res: Resource, body: dict, *, creating: bool) -> dict:
    known = {f.name: f for f in res.fields}
    extra = set(body) - set(known)
    if extra:
        raise _invalid(f"알 수 없는 항목: {', '.join(sorted(extra))}")
    values: dict[str, Any] = {}
    for f in res.fields:
        if f.name in body:
            values[f.name] = clean_value(f, body[f.name])
        elif creating:
            default = f.default
            if default is None:
                if f.required:
                    raise _invalid(f"{f.label or f.name}: 비울 수 없는 항목입니다")
                continue
            values[f.name] = clean_value(f, default)
    return values


def get_resource(key: str) -> Resource:
    res = BY_KEY.get(key)
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "알 수 없는 항목 종류입니다")
    return res


def ensure_mine(conn: Connection, work_id: int, account_id: int) -> None:
    if conn.execute(
        'SELECT 1 FROM "작품" WHERE "번호" = %s AND "계정_번호" = %s', (work_id, account_id)
    ).fetchone() is None:
        raise not_found()


def select_rows(conn: Connection, res: Resource, work_id: int) -> list[dict]:
    cols = sql.SQL(", ").join(sql.Identifier(c) for c in columns(res))
    rows = conn.execute(
        sql.SQL('SELECT {cols} FROM {t} WHERE "작품_번호" = %s ORDER BY {k}').format(
            cols=cols, t=sql.Identifier(res.table), k=sql.Identifier(key_col(res))
        ),
        (work_id,),
    ).fetchall()
    return with_materials(conn, res, work_id, rows)


def fetch_one(conn: Connection, res: Resource, work_id: int, item_id: int) -> dict:
    cols = sql.SQL(", ").join(sql.Identifier(c) for c in columns(res))
    row = conn.execute(
        sql.SQL('SELECT {cols} FROM {t} WHERE "작품_번호" = %s AND {k} = %s').format(
            cols=cols, t=sql.Identifier(res.table), k=sql.Identifier(key_col(res))
        ),
        (work_id, item_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{res.label}을(를) 찾을 수 없습니다")
    return with_materials(conn, res, work_id, [row])[0]


MATERIAL_COLUMNS = {"단서": "단서_순서", "증언": "증언_순서", "조합": "조합_순서"}
MAX_MATERIALS = 50


def combo_materials(conn: Connection, work_id: int) -> dict[int, list[dict]]:
    """조합 순서 → 재료 목록([{종류, 순서}], 넣은 순서대로). 화면은 조합 하나를 만들 때 재료를 함께 고르므로 조합에 붙여서 내려 준다."""
    out: dict[int, list[dict]] = {}
    for row in conn.execute(
        'SELECT "결과_조합_순서", "단서_순서", "증언_순서", "조합_순서" FROM "조합재료" WHERE "작품_번호" = %s ORDER BY "번호"', (work_id,)
    ).fetchall():
        kind = next(k for k, col in MATERIAL_COLUMNS.items() if row[col] is not None)
        out.setdefault(row["결과_조합_순서"], []).append({"종류": kind, "순서": row[MATERIAL_COLUMNS[kind]]})
    return out


def with_materials(conn: Connection, res: Resource, work_id: int, rows: list[dict]) -> list[dict]:
    if res.key != "combos":
        return rows
    by_combo = combo_materials(conn, work_id)
    return [{**r, "재료": by_combo.get(r["순서"], [])} for r in rows]


def clean_materials(conn: Connection, work_id: int, raw: Any, combo_order: int | None) -> list[dict]:
    """조합의 재료 목록을 검사한다. 같은 재료를 여러 번 넣어도 한 번만 남고, 없는 재료나 순환(자기 자신 포함)은 거부한다."""
    if not isinstance(raw, list):
        raise _invalid("재료: 목록으로 입력해 주세요")
    if len(raw) > MAX_MATERIALS * 4:
        raise _invalid(f"재료는 {MAX_MATERIALS}개까지 넣을 수 있습니다")
    seen: set[tuple[str, int]] = set()
    parts: list[dict] = []
    for item in raw:
        if not isinstance(item, dict) or item.get("종류") not in MATERIAL_COLUMNS:
            raise _invalid("재료: 단서·증언·조합 중 하나여야 합니다")
        order = item.get("순서")
        if isinstance(order, bool) or not isinstance(order, int) or order < 1:
            raise _invalid("재료: 번호를 읽을 수 없습니다")
        key = (item["종류"], order)
        if key in seen:
            continue                                                  # 같은 재료는 한 번만 참조한다
        seen.add(key)
        parts.append({"종류": item["종류"], "순서": order})
    if len(parts) > MAX_MATERIALS:
        raise _invalid(f"재료는 {MAX_MATERIALS}개까지 넣을 수 있습니다")
    for kind, table in (("단서", "단서"), ("증언", "증언"), ("조합", "조합")):
        wanted = [p["순서"] for p in parts if p["종류"] == kind]
        if wanted:
            found = {
                r["순서"] for r in conn.execute(
                    sql.SQL('SELECT "순서" FROM {t} WHERE "작품_번호" = %s AND "순서" = ANY(%s)').format(t=sql.Identifier(table)),
                    (work_id, wanted),
                ).fetchall()
            }
            if found != set(wanted):
                raise _invalid(f"재료: 이 작품에 없는 {kind}입니다")
    combos = [p["순서"] for p in parts if p["종류"] == "조합"]
    if combo_order is not None and combo_order in combos:
        raise _invalid("재료: 조합이 자기 자신을 재료로 쓸 수 없습니다")
    if combos and combo_order is not None:
        # 다른 조합들의 재료 관계에서, 재료로 고른 조합들이 거슬러 올라가다 이 조합에 닿으면 순환이다.
        uses: dict[int, list[int]] = {}
        for row in conn.execute(
            'SELECT "결과_조합_순서", "조합_순서" FROM "조합재료" WHERE "작품_번호" = %s AND "조합_순서" IS NOT NULL AND "결과_조합_순서" <> %s',
            (work_id, combo_order),
        ).fetchall():
            uses.setdefault(row["결과_조합_순서"], []).append(row["조합_순서"])
        stack, visited = list(combos), set()
        while stack:
            cur = stack.pop()
            if cur == combo_order:
                raise _invalid("재료: 조합이 서로를 재료로 쓰는 순환이 됩니다")
            if cur in visited:
                continue
            visited.add(cur)
            stack.extend(uses.get(cur, []))
    return parts


def save_materials(conn: Connection, work_id: int, combo_order: int, parts: list[dict]) -> None:
    """조합의 재료를 통째로 바꾼다(DB 에는 조합재료 행으로 나눠 저장한다)."""
    conn.execute('DELETE FROM "조합재료" WHERE "작품_번호" = %s AND "결과_조합_순서" = %s', (work_id, combo_order))
    for part in parts:
        conn.execute(
            sql.SQL('INSERT INTO "조합재료" ("작품_번호", "결과_조합_순서", {c}) VALUES (%s, %s, %s)').format(
                c=sql.Identifier(MATERIAL_COLUMNS[part["종류"]])
            ),
            (work_id, combo_order, part["순서"]),
        )


def check_library_access(conn: Connection, res: Resource, values: dict, account_id: int) -> None:
    """페이즈에 연결하는 진행단계·기믹은 공통 항목이거나 내 것이고 삭제되지 않은 것이어야 한다."""
    table = LIBRARY_TABLE.get(res.key)
    if table is None:
        return
    col = next(f.name for f in res.fields if f.kind == "libref")
    if col not in values:
        return
    ok = conn.execute(
        sql.SQL('SELECT 1 FROM {t} WHERE "번호" = %s AND ("계정_번호" IS NULL OR "계정_번호" = %s) AND "삭제일시" IS NULL').format(
            t=sql.Identifier(table)
        ),
        (values[col], account_id),
    ).fetchone()
    if ok is None:
        raise _invalid(f"{(next(f for f in res.fields if f.name == col).label)}: 사용할 수 없는 항목입니다 (없거나 삭제되었거나 남의 비공개 항목)")


CHECK_MESSAGES = {
    "ck_조합재료_재료하나": "재료는 단서·증언·조합 중 정확히 하나를 골라야 합니다",
    "ck_진행순서_진행시간": "진행 시간은 0 이상이어야 합니다",
}


def translate_db_error(exc: errors.Error, *, deleting: bool = False) -> HTTPException:
    """제약 위반을 사용자가 이해할 수 있는 응답으로 바꾼다."""
    if isinstance(exc, errors.ForeignKeyViolation):
        if deleting:
            return HTTPException(status.HTTP_409_CONFLICT, "다른 항목이 이 항목을 사용하고 있어 지울 수 없습니다. 먼저 연결을 끊어 주세요")
        return _invalid("연결하려는 항목이 이 작품에 없습니다")
    if isinstance(exc, errors.UniqueViolation):
        return HTTPException(status.HTTP_409_CONFLICT, "이미 있는 항목입니다")
    if isinstance(exc, errors.CheckViolation):
        return _invalid(CHECK_MESSAGES.get(exc.diag.constraint_name or "", "입력값이 규칙에 맞지 않습니다"))
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "저장하지 못했습니다")


def touch_work(conn: Connection, work_id: int) -> None:
    conn.execute('UPDATE "작품" SET "수정일시" = CURRENT_TIMESTAMP WHERE "번호" = %s', (work_id,))


def card_display_names(cards: list[dict], names: dict[int, str]) -> dict[int, str]:
    """칸에 놓인 진행단계 카드(진행구성 행)의 표시 이름. 키는 진행구성 번호.

    기본은 진행단계 이름 그대로이고, 같은 이름이 한 작품에 둘 이상 놓이면 칸 위치 순서대로 "1차 이름", "2차 이름"이 된다.
    같은 칸에 같은 이름이 둘일 수는 없다(UNIQUE). 저장하지 않고 읽을 때마다 계산한다.
    """
    counts = Counter(names[c["진행단계_번호"]] for c in cards)
    seen: Counter = Counter()
    out: dict[int, str] = {}
    for c in sorted(cards, key=lambda c: (c["진행순서_순서"], c["번호"])):
        name = names[c["진행단계_번호"]]
        if counts[name] > 1:
            seen[name] += 1
            out[c["번호"]] = f"{seen[name]}차 {name}"
        else:
            out[c["번호"]] = name
    return out


def phase_display_names(phases: list[dict], cards: list[dict]) -> dict[int, str | None]:
    """페이즈(칸)의 표시 이름. 키는 칸 번호(순서).

    제작자가 이름을 정했으면 그것, 비워 두었으면 **붙은 진행단계 이름을 가운데점으로 이어** 따라간다("조사·밀담").
    진행단계도 없으면 None. 저장하지 않고 읽을 때마다 계산하므로, 카드를 바꾸면 이름도 따라 바뀐다.
    cards 는 진행구성 행(표시이름 포함)이며 주어진 순서대로 잇는다.
    """
    by_slot: dict[int, list[str]] = {}
    for c in cards:
        by_slot.setdefault(c["진행순서_순서"], []).append(c["표시이름"])
    out: dict[int, str | None] = {}
    for p in phases:
        custom = (p.get("이름") or "").strip()
        out[p["순서"]] = custom or "·".join(by_slot.get(p["순서"], [])) or None
    return out


def declared(rule: Any) -> dict | None:
    """진행단계 스크립트가 정한 제작 화면(설정 칸과 조건 항목). 정하지 않았거나 읽을 수 없으면 None."""
    from .cards import known_names
    from .declare import declarations
    from .script import ScriptError

    source = rule.get("스크립트") if isinstance(rule, dict) else None
    if not isinstance(source, str):
        return None
    try:
        return declarations(source, known_names())
    except ScriptError:
        return None


KNOWN_SETTINGS = ("개인서사공개", "내용유지", "후보", "질문", "횟수", "보여주기허용", "양도허용", "동률", "재투표후보", "재투표한도", "대상", "안내")


def used_settings(rule: Any) -> list[str]:
    """진행단계 스크립트가 글자로 가리키는 알려진 카드 설정 이름. 스크립트를 실행하지 않고 글에서 찾는다."""
    source = rule.get("스크립트") if isinstance(rule, dict) else None
    if not isinstance(source, str):
        return []
    return [key for key in KNOWN_SETTINGS if f'"{key}"' in source or f"'{key}'" in source]       # 설정 이름을 글자로 적은 곳만 센다


@router.get("")
def content_bundle(work_id: int, conn: Conn, me: CurrentUser) -> dict:
    """작품의 모든 콘텐츠를 한 번에 돌려준다. 화면이 서로 가리키는 항목의 이름을 보여 주는 데 쓴다."""
    ensure_mine(conn, work_id, me.계정.번호)
    out: dict[str, Any] = {r.key: select_rows(conn, r, work_id) for r in RESOURCES}
    out["characters"] = conn.execute(
        'SELECT "순서", "이름", "직업", "NPC", "범인", "서사" FROM "인물" WHERE "작품_번호" = %s ORDER BY "순서"', (work_id,)
    ).fetchall()
    story = conn.execute('SELECT "공통스토리" FROM "작품" WHERE "번호" = %s', (work_id,)).fetchone()["공통스토리"]
    out["story"] = {"공통스토리_부분수": len(narrative.split(story or ""))}              # 공통 스토리 카드가 고를 부분 번호의 범위를 알려면 개수가 필요하다
    for person in out["characters"]:
        person["서사_부분수"] = len(narrative.split(person.pop("서사")))      # 프로필 숙지 설정 화면이 고를 번호를 알려면 개수가 필요하다
    # 이 작품이 연결한 라이브러리 항목의 이름·버전·삭제 여부 (삭제된 항목은 '삭제된 항목'으로 표시하려고)
    out["library"] = {
        "phases": {
            row["번호"]: row
            for row in conn.execute(
                'SELECT "번호", "이름", "버전", "설명", "삭제일시" IS NOT NULL AS "삭제됨", "규칙" FROM "진행단계" '
                'WHERE "번호" IN (SELECT "진행단계_번호" FROM "진행구성" WHERE "작품_번호" = %s)', (work_id,)
            ).fetchall()
        },
        "gimmicks": {
            row["번호"]: row
            for row in conn.execute(
                'SELECT "번호", "이름", "버전", "설명", "삭제일시" IS NOT NULL AS "삭제됨" FROM "기믹" '
                'WHERE "번호" IN (SELECT "기믹_번호" FROM "기믹적용" WHERE "작품_번호" = %s)', (work_id,)
            ).fetchall()
        },
    }
    for row in out["library"]["phases"].values():
        # 제작 화면: 스크립트가 설정정의·조건정의로 정한 입력칸과 조건. 없으면 스크립트가 글자로 가리키는 설정 이름만 쓴다.
        rule = row.pop("규칙")
        decl = declared(rule)
        row["설정정의"] = decl["설정"] if decl else None
        row["조건정의"] = decl["조건"] if decl else []
        row["사용설정"] = [s["키"] for s in decl["설정"]] if decl else used_settings(rule)
    names = {n: row["이름"] for n, row in out["library"]["phases"].items()}
    shown = card_display_names(out["phase-steps"], names)
    for card in out["phase-steps"]:
        card["표시이름"] = shown[card["번호"]]
    names_by_slot = phase_display_names(out["phases"], out["phase-steps"])
    for phase in out["phases"]:
        phase["표시이름"] = names_by_slot[phase["순서"]]
    return out


@router.get("/{key}")
def list_items(work_id: int, key: str, conn: Conn, me: CurrentUser) -> list[dict]:
    res = get_resource(key)
    ensure_mine(conn, work_id, me.계정.번호)
    return select_rows(conn, res, work_id)


@router.post("/{key}", status_code=status.HTTP_201_CREATED)
def create_item(work_id: int, key: str, conn: Conn, me: CurrentUser, body: dict[str, Any] = Body(...)) -> dict:
    res = get_resource(key)
    lock_work(conn, work_id, me.계정.번호)
    parts_raw = body.pop("재료", None) if res.has_parts else None
    values = clean_body(res, body, creating=True)
    check_library_access(conn, res, values, me.계정.번호)
    parts = clean_materials(conn, work_id, parts_raw, None) if parts_raw is not None else None
    cols = ["작품_번호"]
    params: list[Any] = [work_id]
    if res.ordered:
        cols.append("순서")
        params.append(next_order(conn, res.table, work_id))
    cols += list(values)
    params += list(values.values())
    try:
        row = conn.execute(
            sql.SQL('INSERT INTO {t} ({cols}) VALUES ({ph}) RETURNING {ret}').format(
                t=sql.Identifier(res.table),
                cols=sql.SQL(", ").join(sql.Identifier(c) for c in cols),
                ph=sql.SQL(", ").join(sql.Placeholder() for _ in cols),
                ret=sql.SQL(", ").join(sql.Identifier(c) for c in columns(res)),
            ),
            params,
        ).fetchone()
    except errors.Error as exc:
        raise translate_db_error(exc) from exc
    if parts is not None:
        try:
            save_materials(conn, work_id, row["순서"], parts)
        except errors.Error as exc:
            raise translate_db_error(exc) from exc
    touch_work(conn, work_id)
    return with_materials(conn, res, work_id, [row])[0]


@router.patch("/{key}/{item_id}")
def update_item(work_id: int, key: str, item_id: int, conn: Conn, me: CurrentUser, body: dict[str, Any] = Body(...)) -> dict:
    res = get_resource(key)
    lock_work(conn, work_id, me.계정.번호)
    current = fetch_one(conn, res, work_id, item_id)
    parts_raw = body.pop("재료", None) if res.has_parts else None
    changes = clean_body(res, body, creating=False)
    check_library_access(conn, res, changes, me.계정.번호)
    parts = clean_materials(conn, work_id, parts_raw, item_id) if parts_raw is not None else None
    if parts is not None:
        try:
            save_materials(conn, work_id, item_id, parts)
        except errors.Error as exc:
            raise translate_db_error(exc) from exc
    if not changes:
        touch_work(conn, work_id)
        return fetch_one(conn, res, work_id, item_id)
    try:
        row = conn.execute(
            sql.SQL('UPDATE {t} SET {sets} WHERE "작품_번호" = %s AND {k} = %s RETURNING {ret}').format(
                t=sql.Identifier(res.table),
                sets=sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(c)) for c in changes),
                k=sql.Identifier(key_col(res)),
                ret=sql.SQL(", ").join(sql.Identifier(c) for c in columns(res)),
            ),
            (*changes.values(), work_id, item_id),
        ).fetchone()
    except errors.Error as exc:
        raise translate_db_error(exc) from exc
    touch_work(conn, work_id)
    return with_materials(conn, res, work_id, [row])[0]


@router.delete("/{key}/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(work_id: int, key: str, item_id: int, conn: Conn, me: CurrentUser) -> None:
    res = get_resource(key)
    lock_work(conn, work_id, me.계정.번호)
    fetch_one(conn, res, work_id, item_id)
    try:
        conn.execute(
            sql.SQL('DELETE FROM {t} WHERE "작품_번호" = %s AND {k} = %s').format(
                t=sql.Identifier(res.table), k=sql.Identifier(key_col(res))
            ),
            (work_id, item_id),
        )
    except errors.Error as exc:
        raise translate_db_error(exc, deleting=True) from exc
    touch_work(conn, work_id)
