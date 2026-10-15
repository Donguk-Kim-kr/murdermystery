"""재사용 라이브러리 API (진행단계 / 기믹). docs/DB_RULES.md B39.

* 항목의 내용은 수정하지 않는다. 고치려면 **같은 이름으로 만들면** 그 계열의 다음 버전이 된다
  (새 버전 번호 = 그 계열의 최대 버전 + 1, 삭제된 행도 센다).
* 계열의 식별자는 (계정, 이름)이다. 공통(시스템 제공) 항목은 계정이 없고, **운영자만** 만들거나 지울 수 있다.
* 삭제는 행을 지우지 않는 삭제 표시이다. 버전 하나 또는 같은 이름의 모든 버전을 삭제할 수 있다.
* 이름 변경은 계열 전체(모든 버전)를 한꺼번에 바꾼다. 같은 이름의 계열이 이미 있으면 거부한다.
* 선택할 수 있는 것은 공통 항목과 내 항목뿐이다. `공개여부`는 나중에 제작자끼리 공유할 때 쓰며 지금은 값만 저장한다.
"""
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import APIRouter, Body, HTTPException, Query, status
from psycopg import Connection, errors, sql
from psycopg.types.json import Jsonb

from .auth import CurrentUser
from .db import Conn


@dataclass(frozen=True)
class Kind:
    table: str
    label: str
    content: tuple[str, ...]  # 내용 칸 (JSON 객체, 필수)
    description_required: bool


KINDS = {
    "phases": Kind("진행단계", "진행단계", ("규칙",), True),
    "gimmicks": Kind("기믹", "기믹", ("조건", "결과"), False),
}
BASE = ("번호", "계정_번호", "이름", "설명", "버전", "변경내역", "삭제일시", "공개여부")

router = APIRouter(prefix="/api/library", tags=["library"])


def _kind(name: str) -> Kind:
    kind = KINDS.get(name)
    if kind is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "알 수 없는 라이브러리 종류입니다")
    return kind


def _is_operator(me: CurrentUser) -> bool:
    return me.계정.권한 == "운영자"


def _cols(kind: Kind) -> sql.Composed:
    return sql.SQL(", ").join(sql.Identifier(c) for c in (*BASE, *kind.content))


def _present(row: dict) -> dict:
    return {**row, "공통": row["계정_번호"] is None}


def _invalid(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def _text(body: dict, name: str, *, required: bool, max_len: int) -> str | None:
    value = body.get(name)
    if value is None or (isinstance(value, str) and value.strip() == ""):
        if required:
            raise _invalid(f"{name}: 비울 수 없는 항목입니다")
        return None
    if not isinstance(value, str):
        raise _invalid(f"{name}: 글자로 입력해 주세요")
    if len(value) > max_len:
        raise _invalid(f"{name}: {max_len}자를 넘을 수 없습니다")
    return value.strip() if name == "이름" else value


def _load(conn: Connection, kind: Kind, item_id: int, me: CurrentUser) -> dict:
    """내 항목이거나 공통 항목이면 돌려준다. 남의 항목은 존재 여부를 숨긴다."""
    row = conn.execute(
        sql.SQL('SELECT {c} FROM {t} WHERE "번호" = %s AND ("계정_번호" IS NULL OR "계정_번호" = %s)').format(
            c=_cols(kind), t=sql.Identifier(kind.table)
        ),
        (item_id, me.계정.번호),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{kind.label} 항목을 찾을 수 없습니다")
    return row


def _ensure_may_change(row: dict, me: CurrentUser) -> None:
    if row["계정_번호"] is None and not _is_operator(me):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "공통 항목은 운영자만 바꿀 수 있습니다")


@router.get("/{kind}")
def list_items(kind: str, conn: Conn, me: CurrentUser, include_deleted: bool = Query(default=False)) -> list[dict]:
    k = _kind(kind)
    rows = conn.execute(
        sql.SQL(
            'SELECT {c} FROM {t} WHERE ("계정_번호" IS NULL OR "계정_번호" = %s)'
            + ("" if include_deleted else ' AND "삭제일시" IS NULL')
            + ' ORDER BY "이름", "버전" DESC'
        ).format(c=_cols(k), t=sql.Identifier(k.table)),
        (me.계정.번호,),
    ).fetchall()
    return [_present(r) for r in rows]


@router.post("/{kind}", status_code=status.HTTP_201_CREATED)
def create_item(kind: str, conn: Conn, me: CurrentUser, body: dict[str, Any] = Body(...)) -> dict:
    k = _kind(kind)
    allowed = {"이름", "설명", "변경내역", "공통", *k.content}
    extra = set(body) - allowed
    if extra:
        raise _invalid(f"알 수 없는 항목: {', '.join(sorted(extra))}")
    name = _text(body, "이름", required=True, max_len=100)
    description = _text(body, "설명", required=False, max_len=2000)
    change = _text(body, "변경내역", required=False, max_len=2000)
    contents = {}
    for col in k.content:
        value = body.get(col, {})
        if not isinstance(value, dict):
            raise _invalid(f"{col}: JSON 객체({{...}})로 입력해 주세요")
        contents[col] = Jsonb(value)
    common = body.get("공통", False)
    if not isinstance(common, bool):
        raise _invalid("공통: 켜짐/꺼짐으로 입력해 주세요")
    if common and not _is_operator(me):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "공통 항목은 운영자만 만들 수 있습니다")
    owner = None if common else me.계정.번호
    # 같은 계정·이름의 다음 버전. 삭제된 행도 세므로 번호를 다시 쓰지 않는다.
    last = conn.execute(
        sql.SQL('SELECT COALESCE(MAX("버전"), 0) AS v FROM {t} WHERE "계정_번호" IS NOT DISTINCT FROM %s AND "이름" = %s').format(
            t=sql.Identifier(k.table)
        ),
        (owner, name),
    ).fetchone()["v"]
    cols = ["계정_번호", "이름", "설명", "버전", "변경내역", *k.content]
    # 진행단계의 설명 칸은 NULL 을 받지 않지만 빈 글자는 받는다 (비워 두어도 만들 수 있게).
    values = [owner, name, description if description is not None else ("" if k.description_required else None),
              last + 1, change, *contents.values()]
    try:
        row = conn.execute(
            sql.SQL("INSERT INTO {t} ({cols}) VALUES ({ph}) RETURNING {ret}").format(
                t=sql.Identifier(k.table),
                cols=sql.SQL(", ").join(sql.Identifier(c) for c in cols),
                ph=sql.SQL(", ").join(sql.Placeholder() for _ in cols),
                ret=_cols(k),
            ),
            values,
        ).fetchone()
    except errors.UniqueViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, "같은 이름의 같은 버전이 이미 있습니다. 다시 시도해 주세요") from None
    return _present(row)


@router.patch("/{kind}/{item_id}")
def update_item(kind: str, item_id: int, conn: Conn, me: CurrentUser, body: dict[str, Any] = Body(...)) -> dict:
    """이름 변경(계열 전체)과 공개 여부 켜고 끄기. 내용은 바꿀 수 없다 (새 버전을 만든다)."""
    k = _kind(kind)
    extra = set(body) - {"이름", "공개여부"}
    if extra:
        raise _invalid(f"바꿀 수 없는 항목: {', '.join(sorted(extra))} (내용은 같은 이름으로 새 버전을 만드세요)")
    row = _load(conn, k, item_id, me)
    _ensure_may_change(row, me)
    owner = row["계정_번호"]
    if "이름" in body:
        new_name = _text(body, "이름", required=True, max_len=100)
        if new_name != row["이름"]:
            clash = conn.execute(
                sql.SQL('SELECT 1 FROM {t} WHERE "계정_번호" IS NOT DISTINCT FROM %s AND "이름" = %s LIMIT 1').format(
                    t=sql.Identifier(k.table)
                ),
                (owner, new_name),
            ).fetchone()
            if clash:
                raise HTTPException(status.HTTP_409_CONFLICT, "같은 이름의 항목이 이미 있습니다")
            conn.execute(
                sql.SQL('UPDATE {t} SET "이름" = %s WHERE "계정_번호" IS NOT DISTINCT FROM %s AND "이름" = %s').format(
                    t=sql.Identifier(k.table)
                ),
                (new_name, owner, row["이름"]),
            )
    if "공개여부" in body:
        flag = body["공개여부"]
        if not isinstance(flag, bool):
            raise _invalid("공개여부: 켜짐/꺼짐으로 입력해 주세요")
        conn.execute(
            sql.SQL('UPDATE {t} SET "공개여부" = %s WHERE "번호" = %s').format(t=sql.Identifier(k.table)), (flag, item_id)
        )
    return _present(_load(conn, k, item_id, me))


@router.delete("/{kind}/{item_id}")
def delete_item(
    kind: str, item_id: int, conn: Conn, me: CurrentUser,
    scope: Literal["version", "lineage"] = Query(default="version"),
) -> dict:
    """삭제 표시를 한다. 행과 이미 확정된 스냅샷은 남고, 앞으로 새로 선택할 수 없다."""
    k = _kind(kind)
    row = _load(conn, k, item_id, me)
    _ensure_may_change(row, me)
    if scope == "version":
        where, params = sql.SQL('"번호" = %s'), (item_id,)
    else:
        where, params = sql.SQL('"계정_번호" IS NOT DISTINCT FROM %s AND "이름" = %s'), (row["계정_번호"], row["이름"])
    done = conn.execute(
        sql.SQL('UPDATE {t} SET "삭제일시" = CURRENT_TIMESTAMP WHERE {w} AND "삭제일시" IS NULL').format(
            t=sql.Identifier(k.table), w=where
        ),
        params,
    ).rowcount
    if done == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 삭제된 항목입니다")
    return {"삭제됨": done}
