"""진행단계 스크립트 검사 API. 편집기가 저장 전에 문법·허용 여부·없는 이름을 확인하는 데 쓴다 (docs/ENGINE_DESIGN.md 1-9).

스크립트를 실행하지는 않는다. 검사 규칙은 게임이 시작할 때·확정할 때 쓰는 것과 같다(`cards.known_names`).
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from .auth import CurrentUser
from .cards import CONSTANT_NAMES, FUNCTION_NAMES, known_names
from .script import ScriptError, builtin_names, compile_source

router = APIRouter(prefix="/api/scripts", tags=["scripts"])

MAX_SCRIPT_CHARS = 50000


class ScriptCheckIn(BaseModel):
    스크립트: str = Field(max_length=MAX_SCRIPT_CHARS)


class ScriptCheckOut(BaseModel):
    정상: bool
    오류: str | None
    줄: int | None
    함수: list[str]
    """스크립트가 정의한 함수 이름(`실행`, `진행조건` 등)."""


@router.post("/check", response_model=ScriptCheckOut)
def check_script(body: ScriptCheckIn, me: CurrentUser) -> ScriptCheckOut:
    if not body.스크립트.strip():
        return ScriptCheckOut(정상=True, 오류=None, 줄=None, 함수=[])
    try:
        program = compile_source(body.스크립트, known_names())
    except ScriptError as err:
        return ScriptCheckOut(정상=False, 오류=err.message, 줄=err.line, 함수=[])
    return ScriptCheckOut(정상=True, 오류=None, 줄=None, 함수=sorted(program.funcs))


class ScriptReferenceOut(BaseModel):
    함수: list[str]
    상수: list[str]
    기본_함수: list[str]


@router.get("/reference", response_model=ScriptReferenceOut)
def script_reference(me: CurrentUser) -> ScriptReferenceOut:
    """스크립트에서 부를 수 있는 이름들(편집기의 도움말용)."""
    return ScriptReferenceOut(함수=sorted(FUNCTION_NAMES), 상수=sorted(CONSTANT_NAMES), 기본_함수=sorted(builtin_names()))
