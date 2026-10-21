"""대기실의 "AI 추가" API (사용자 요청 2026-10-21, 시연용).

방장이 대기실에서 버튼을 누를 때마다 AI 플레이어가 한 명씩 입장한다. 서버는 AI 러너를 자식 프로세스로 띄울 뿐이고(`ai_runner.py`),
AI 는 일반 계정으로 접속해 사람과 같은 API 로 플레이한다. `MM_AI_ENABLED` 가 꺼져 있으면(기본) 쓸 수 없다.
"""
import os
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from .auth import CurrentUser
from .config import get_settings
from .db import Conn
from .rooms import find_my_room, registry

router = APIRouter(prefix="/api", tags=["ai"])


def model_name() -> str:
    return os.environ.get("MM_AI_MODEL", "claude-haiku-5-5")


def has_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def runner_url() -> str:
    return get_settings().ai_url or f"http://127.0.0.1:{os.environ.get('PORT', '8000')}"


class AiStatusOut(BaseModel):
    사용가능: bool          # 서버가 AI 추가를 허용한다(MM_AI_ENABLED)
    모델사용가능: bool      # 서버에 ANTHROPIC_API_KEY 가 있어 모델을 쓰는 AI 를 부를 수 있다
    모델: str


class AiAddIn(BaseModel):
    # claude: 모델을 쓰는 AI(말투를 살려 대화한다, 비용이 든다), simple: 규칙으로만 움직이는 AI(키가 필요 없다). 비우면 키가 있을 때 claude
    방식: Literal["claude", "simple"] | None = None


class AiAddOut(BaseModel):
    닉네임: str
    방식: str


@router.get("/ai/status", response_model=AiStatusOut)
def ai_status(me: CurrentUser) -> AiStatusOut:
    return AiStatusOut(사용가능=get_settings().ai_enabled, 모델사용가능=has_key(), 모델=model_name())


@router.post("/rooms/me/ai", status_code=status.HTTP_202_ACCEPTED, response_model=AiAddOut)
def add_ai(body: AiAddIn, conn: Conn, me: CurrentUser, request: Request) -> AiAddOut:
    """내 대기실에 AI 한 명을 부른다(방장만). AI 는 몇 초 안에 입장하고, 게임이 시작되면 플레이한다."""
    if not get_settings().ai_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "이 서버에서는 AI 추가를 쓸 수 없습니다")
    mine = find_my_room(conn, registry(request), me)
    if mine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "참여 중인 방이 없습니다")
    row, room = mine
    if room.host_id != me.계정.번호:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "방장만 AI 를 추가할 수 있습니다")
    if row["상태"] != "대기":
        raise HTTPException(status.HTTP_409_CONFLICT, "게임이 시작된 방에는 AI 를 추가할 수 없습니다")
    brain = body.방식 or ("claude" if has_key() else "simple")
    if brain == "claude" and not has_key():
        raise HTTPException(status.HTTP_409_CONFLICT, "서버에 ANTHROPIC_API_KEY 가 없어 모델을 쓰는 AI 는 부를 수 없습니다(규칙으로 움직이는 간단한 AI 는 부를 수 있습니다)")

    runner = request.app.state.ai_runner
    taken = {m.nickname for m in room.members.values()}
    if room.player_count() + runner.pending(row["번호"], taken) >= row["최대인원"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "자리가 가득 찼습니다")
    nickname = runner.next_nickname(row["번호"], taken)
    try:
        runner.spawn(row["번호"], row["입장코드"], nickname, brain)
    except RuntimeError as err:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(err)) from None
    return AiAddOut(닉네임=nickname, 방식=brain)
