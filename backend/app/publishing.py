"""작품 공개/비공개 전환 (docs/DB_RULES.md B35). 규칙 자체는 `visibility.py`.

관리자·운영자는 남의 작품도 이 API 로 비공개 처리할 수 있다. 작품 내용(범인·비밀 포함)을 보거나 고치는 권한은
여기서 주지 않는다 — 그 API 는 계속 제작자만 쓸 수 있다.
"""
from fastapi import APIRouter, HTTPException, status

from .auth import CurrentUser
from .db import Conn
from .visibility import publish_denied_reason
from .works import WORK_COLUMNS, WorkOut, load_work_for_actor

router = APIRouter(prefix="/api/works", tags=["publishing"])


def ensure_can_publish(work: dict) -> None:
    """B10: 공개 가능 조건.

    * 확정된 버전이 있어야 한다 (사용자 결정). 확정 버전이 없으면 게임을 시작할 수도 없다.
    * 상태 `완료` 검사는 상태 전이(B6) 기능과 함께 넣는다. 아직 상태를 바꿀 방법이 없다.
    * 확정 전 논리·스토리 검증 툴은 미확정이다 (docs/BACKLOG.md).
    """
    if not work["확정버전_있음"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "확정된 버전이 없는 작품은 공개할 수 없습니다")


def _update(conn, work_id: int, **columns) -> dict:
    assignments = ", ".join(f'"{c}" = %s' for c in columns)
    return conn.execute(
        f'UPDATE "작품" SET {assignments} WHERE "번호" = %s RETURNING {WORK_COLUMNS}',
        (*columns.values(), work_id),
    ).fetchone()


@router.post("/{work_id}/publish", response_model=WorkOut)
def publish(work_id: int, conn: Conn, me: CurrentUser) -> dict:
    work, level, is_owner = load_work_for_actor(conn, work_id, me, lock=True)
    if work["공개여부"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 공개된 작품입니다")
    reason = publish_denied_reason(work["공개권한"], level, is_owner)
    if reason:
        raise HTTPException(status.HTTP_403_FORBIDDEN, reason)
    ensure_can_publish(work)
    # 공개 중에는 공개권한이 쓰이지 않는다. 다음 비공개 때 비공개한 사람의 단계로 다시 정해진다.
    return _update(conn, work_id, 공개여부=True, 공개권한="제작자")


@router.post("/{work_id}/unpublish", response_model=WorkOut)
def unpublish(work_id: int, conn: Conn, me: CurrentUser) -> dict:
    work, level, _ = load_work_for_actor(conn, work_id, me, lock=True)
    if not work["공개여부"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 비공개인 작품입니다")
    return _update(conn, work_id, 공개여부=False, 공개권한=level)


@router.post("/{work_id}/return-to-owner", response_model=WorkOut)
def return_publish_right_to_owner(work_id: int, conn: Conn, me: CurrentUser) -> dict:
    """관리자·운영자가 비공개한 작품의 공개권한을 제작자에게 돌려준다."""
    work, level, is_owner = load_work_for_actor(conn, work_id, me, lock=True)
    if work["공개여부"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "공개 중인 작품입니다")
    if work["공개권한"] == "제작자":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 제작자에게 공개 권한이 있습니다")
    reason = publish_denied_reason(work["공개권한"], level, is_owner)
    if reason:
        raise HTTPException(status.HTTP_403_FORBIDDEN, reason)
    return _update(conn, work_id, 공개권한="제작자")
