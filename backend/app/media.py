"""작품에 붙는 이미지·영상 (`미디어` 테이블, docs/DB_RULES.md B41, 사용자 결정 2026-10-20).

* 붙일 수 있는 곳: **단서**(이미지), **인물**(캐릭터 이미지), **공통 스토리**(영상), **표지**(작품의 대표 이미지). 한 곳에 하나만 붙고, 다시 올리면 바뀐다.
  표지는 작품 목록에 보이는 작품 자체의 정보라서 확정한 시나리오(스냅샷)에 담지 않고, 확정을 막지도 않는다.
* 받는 형식은 jpg·png·webp 이미지와 mp4 영상뿐이다. 확장자나 보낸 형식 이름이 아니라 **파일 내용**으로 확인한다.
* 파일은 서버 폴더(`MM_MEDIA_DIR`, 도커는 `/app/media` 볼륨)에 **내용 해시를 이름으로** 저장한다. `미디어.경로` 에는 그 이름(키)만 적는다.
  같은 내용은 한 번만 저장되고, 확정한 버전이 가리키는 파일은 이름이 곧 내용이라 바뀌지 않는다. 저장은 이 파일의 `store_*` 에만 모여 있어서
  나중에 다른 저장소(객체 저장소)로 바꿀 때 여기만 고치면 된다.
* 파일 주소는 **서명된 주소**이다. 화면에 보여도 되는 사람에게만 서버가 주소를 만들어 주고(단서 이미지는 그 단서를 가진 사람의 카드에만), 주소에는
  계정·만료 시각·서명이 붙는다. `<img>`·`<video>` 는 로그인 정보를 보낼 수 없어서 주소 자체에 서명을 넣었다.
"""
import hashlib
import hmac
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from psycopg import Connection

from .auth import CurrentUser
from .config import get_settings
from .content import touch_work
from .db import Conn
from .ordering import next_order
from .works import lock_work

router = APIRouter(prefix="/api/works/{work_id}/media", tags=["media"])
file_router = APIRouter(prefix="/api/media", tags=["media"])

# 보낸 형식 -> (확장자, 미디어.유형)
KINDS = {
    "image/jpeg": ("jpg", "이미지"),
    "image/png": ("png", "이미지"),
    "image/webp": ("webp", "이미지"),
    "video/mp4": ("mp4", "영상"),
}
MIME_OF = {ext: mime for mime, (ext, _) in KINDS.items()}
KEY_RE = re.compile(r"^[0-9a-f]{64}\.(jpg|png|webp|mp4)$")
# 대상 이름 -> 미디어의 칸. 공통 스토리와 표지는 번호 없이 참/거짓이다(작품당 하나).
TARGETS = {"단서": "단서_순서", "인물": "인물_순서", "공통스토리": "공통스토리", "표지": "표지"}
FLAG_TARGETS = ("공통스토리", "표지")
ALLOWED_TARGET_TYPE = {"단서": "이미지", "인물": "이미지", "공통스토리": "영상", "표지": "이미지"}
IMAGE_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"avif", b"avis", b"qt  "}
URL_BUCKET_SECONDS = 3600          # 주소는 한 시간 단위로 같게 만들어 브라우저가 파일을 다시 받지 않게 한다
URL_VALID_BUCKETS = 2              # 만든 뒤 1~2시간 동안 쓸 수 있다
CHUNK = 1024 * 1024


# ---- 설정과 저장소 ----

def media_dir() -> Path:
    path = Path(get_settings().media_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def max_bytes(mime: str) -> int:
    s = get_settings()
    return s.media_max_video_bytes if KINDS[mime][1] == "영상" else s.media_max_image_bytes


def sniff(head: bytes) -> str | None:
    """파일 앞부분으로 형식을 알아낸다. 허용한 형식이 아니면 None."""
    if head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp" and head[8:12] not in IMAGE_BRANDS:
        return "video/mp4"
    return None


def store_file(tmp: Path, digest: str, ext: str) -> str:
    """임시 파일을 `내용해시.확장자` 로 옮긴다(이미 있으면 임시 파일을 버린다). 돌려주는 것이 `미디어.경로` 에 적는 키이다."""
    key = f"{digest}.{ext}"
    final = media_dir() / key
    if final.exists():
        tmp.unlink(missing_ok=True)
    else:
        os.replace(tmp, final)
    return key


def file_path(key: str) -> Path | None:
    if not KEY_RE.match(key):
        return None
    path = media_dir() / key
    return path if path.is_file() else None


def file_exists(key: str) -> bool:
    return file_path(key) is not None


# ---- 서명된 주소 ----

def _secret() -> bytes:
    """서명에 쓰는 비밀 값. 저장 폴더에 한 번 만들어 두어 서버를 다시 켜도 주소가 이어진다."""
    path = media_dir() / ".secret"
    try:
        return path.read_bytes()
    except FileNotFoundError:
        value = secrets.token_bytes(32)
        tmp = path.with_suffix(f".{secrets.token_hex(4)}.tmp")
        tmp.write_bytes(value)
        os.replace(tmp, path)
        return path.read_bytes()


def _sign(key: str, account: int, expires: int) -> str:
    return hmac.new(_secret(), f"{key}|{account}|{expires}".encode(), hashlib.sha256).hexdigest()[:32]


def signed_url(key: str, account: int, now: float | None = None) -> str:
    """`key` 파일을 `account` 에게 보여 주는 주소. 한 시간 단위로 같은 주소가 나온다."""
    bucket = int((time.time() if now is None else now) // URL_BUCKET_SECONDS)
    expires = (bucket + URL_VALID_BUCKETS) * URL_BUCKET_SECONDS
    return f"/api/media/{key}?a={account}&e={expires}&s={_sign(key, account, expires)}"


# ---- 확정 스냅샷과 게임에서 쓰는 함수 ----

SNAPSHOT_COLUMNS = ("순서", "단서_순서", "증언_순서", "조합_순서", "진행순서_순서", "인물_순서", "공통스토리", "유형", "경로")


def snapshot_rows(conn: Connection, work_id: int) -> list[dict]:
    """확정 스냅샷에 담는 미디어. 표지는 작품 목록의 정보라서 담지 않는다."""
    return conn.execute(
        'SELECT ' + ", ".join(f'"{c}"' for c in SNAPSHOT_COLUMNS) + ' FROM "미디어" WHERE "작품_번호" = %s AND "표지" IS NOT TRUE ORDER BY "순서"', (work_id,)
    ).fetchall()


def cover_url(key: str | None, viewer: int) -> str | None:
    """표지 파일 키의 주소(보는 사람 `viewer` 용). 표지가 없거나 저장소에 파일이 없으면 None. 표지는 작품 목록을 볼 수 있는 누구에게나 보인다."""
    return signed_url(key, viewer) if key and file_exists(key) else None


def media_key(snapshot: dict, target: str, order: int | None = None) -> str | None:
    """확정 내용에서 그 대상에 붙은 파일의 키. 없으면 None. 대상은 단서·인물(번호가 필요)이나 공통스토리."""
    column = TARGETS[target]
    for row in snapshot.get("미디어") or []:
        if target == "공통스토리":
            if row.get("공통스토리"):
                return row["경로"]
        elif row.get(column) == order:
            return row["경로"]
    return None


def media_url(snapshot: dict, viewer: int, target: str, order: int | None = None) -> str | None:
    """그 대상의 이미지·영상 주소(보는 사람 `viewer` 용). 붙은 파일이 없거나 저장소에 없으면 None."""
    key = media_key(snapshot, target, order)
    if key is None or not file_exists(key):
        return None
    return signed_url(key, viewer)


# ---- 제작 화면용 API ----

def _target_exists(conn: Connection, work_id: int, target: str, order: int | None) -> None:
    if target in FLAG_TARGETS:
        return
    table = "단서" if target == "단서" else "인물"
    if order is None or conn.execute(
        sql_exists(table), (work_id, order)
    ).fetchone() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{target}을(를) 찾을 수 없습니다")


def sql_exists(table: str) -> str:
    assert table in ("단서", "인물")          # 식별자는 이 두 이름만 쓴다
    return f'SELECT 1 FROM "{table}" WHERE "작품_번호" = %s AND "순서" = %s'


def _where(target: str) -> tuple[str, bool]:
    column = TARGETS[target]
    return (f'"{column}" IS TRUE' if target in FLAG_TARGETS else f'"{column}" = %s'), target not in FLAG_TARGETS


def delete_for(conn: Connection, work_id: int, target: str, order: int | None = None) -> int:
    """그 대상에 붙은 미디어 행을 지운다(파일은 다른 확정 버전이 쓸 수 있어 지우지 않는다). 지운 행 수를 돌려준다."""
    where, takes_order = _where(target)
    params: tuple = (work_id, order) if takes_order else (work_id,)
    return conn.execute(f'DELETE FROM "미디어" WHERE "작품_번호" = %s AND {where}', params).rowcount


def _save_row(conn: Connection, work_id: int, account: int, target: str, order: int | None, kind: str, key: str) -> dict:
    lock_work(conn, work_id, account)
    _target_exists(conn, work_id, target, order)
    delete_for(conn, work_id, target, order)
    number = next_order(conn, "미디어", work_id)
    column = TARGETS[target]
    if target in FLAG_TARGETS:
        conn.execute(f'INSERT INTO "미디어" ("작품_번호", "순서", "{column}", "유형", "경로") VALUES (%s, %s, TRUE, %s, %s)',
                     (work_id, number, kind, key))
    else:
        conn.execute(f'INSERT INTO "미디어" ("작품_번호", "순서", "{column}", "유형", "경로") VALUES (%s, %s, %s, %s, %s)',
                     (work_id, number, order, kind, key))
    touch_work(conn, work_id)
    return {"순서": number, "대상": target, "번호": order, "유형": kind, "경로": key}


def _out(row: dict, account: int) -> dict:
    target = next(t for t, c in TARGETS.items() if (row.get(c) if t in FLAG_TARGETS else row.get(c) is not None))
    order = None if target in FLAG_TARGETS else row[TARGETS[target]]
    return {"순서": row["순서"], "대상": target, "번호": order, "유형": row["유형"], "주소": signed_url(row["경로"], account) if file_exists(row["경로"]) else None}


@router.get("")
def list_media(work_id: int, conn: Conn, me: CurrentUser) -> list[dict]:
    """내 작품에 붙은 미디어(제작 화면이 미리보기에 쓴다)."""
    lock_work(conn, work_id, me.계정.번호)
    rows = conn.execute(
        'SELECT "순서", "단서_순서", "인물_순서", "공통스토리", "표지", "유형", "경로" FROM "미디어" WHERE "작품_번호" = %s ORDER BY "순서"', (work_id,)
    ).fetchall()
    return [_out(r, me.계정.번호) for r in rows]


@router.put("", status_code=status.HTTP_201_CREATED)
async def upload(work_id: int, request: Request, conn: Conn, me: CurrentUser, 대상: str, 번호: int | None = None) -> dict:
    """파일 내용을 그대로 보내(`Content-Type` 은 image/jpeg·image/png·image/webp·video/mp4) 대상에 붙인다. 이미 붙은 것은 바뀐다.

    `대상` 은 단서·인물(`번호` 는 그 단서·인물의 순서)·공통스토리·표지이다."""
    if 대상 not in TARGETS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "대상은 단서, 인물, 공통스토리, 표지 중 하나여야 합니다")
    declared = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if declared not in KINDS:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "jpg·png·webp 이미지나 mp4 영상만 올릴 수 있습니다")
    ext, kind = KINDS[declared]
    if kind != ALLOWED_TARGET_TYPE[대상]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{대상}에는 {ALLOWED_TARGET_TYPE[대상]}만 붙일 수 있습니다")
    limit = max_bytes(declared)
    too_big = HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"{kind}은(는) {limit // (1024 * 1024)}MB 까지 올릴 수 있습니다")
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > limit:
        raise too_big
    await run_in_threadpool(lock_work, conn, work_id, me.계정.번호)        # 소유자가 아니면 파일을 받기 전에 거절한다
    await run_in_threadpool(_target_exists, conn, work_id, 대상, 번호)

    tmp = media_dir() / f".upload-{secrets.token_hex(8)}.tmp"
    digest = hashlib.sha256()
    size, head = 0, b""
    try:
        with tmp.open("wb") as out:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise too_big
                if len(head) < 16:
                    head = (head + chunk)[:16]
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "빈 파일입니다")
        if sniff(head) != declared:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "파일 내용이 선택한 형식과 맞지 않습니다")
        key = await run_in_threadpool(store_file, tmp, digest.hexdigest(), ext)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    row = await run_in_threadpool(_save_row, conn, work_id, me.계정.번호, 대상, 번호, kind, key)
    return {**row, "주소": signed_url(key, me.계정.번호)}


@router.delete("/{number}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media(work_id: int, number: int, conn: Conn, me: CurrentUser) -> None:
    lock_work(conn, work_id, me.계정.번호)
    if conn.execute('DELETE FROM "미디어" WHERE "작품_번호" = %s AND "순서" = %s', (work_id, number)).rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "미디어를 찾을 수 없습니다")
    touch_work(conn, work_id)


# ---- 파일 내려주기 ----

@file_router.get("/{key}")
def get_file(key: str, a: int, e: int, s: str) -> FileResponse:
    """서명된 주소로 파일을 내려준다(영상은 구간 이동이 되도록 Range 요청을 받는다)."""
    now = time.time()
    if not KEY_RE.match(key) or e < now or e > now + (URL_VALID_BUCKETS + 1) * URL_BUCKET_SECONDS or not hmac.compare_digest(s, _sign(key, a, e)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "주소가 올바르지 않거나 만료되었습니다")
    path = file_path(key)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일을 찾을 수 없습니다")
    return FileResponse(path, media_type=MIME_OF[key.rsplit(".", 1)[1]],
                        headers={"Cache-Control": f"private, max-age={max(0, min(int(e - now), URL_BUCKET_SECONDS))}", "X-Content-Type-Options": "nosniff"})
