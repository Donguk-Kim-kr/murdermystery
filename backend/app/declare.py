"""진행단계 스크립트가 스스로 정하는 제작 화면 (docs/ENGINE_SPEC.md 10).

스크립트에 두 함수를 두면 제작 화면이 그것을 읽어 그린다. 게임은 돌리지 않고 이 두 함수만 안전하게 실행한다.

* `설정정의(카드)` → 흐름의 카드 설정 화면에 보일 입력칸들(`숫자칸`, `선택칸`, `켜짐칸`, `글칸`, `여러선택칸`, `서사칸`, `후보칸`, `질문칸`)의 목록.
* `조건정의(카드)` → 엔딩·후일담의 조건으로 고를 수 있는 항목들(`조건항목(이름, 식, 인자)`)의 목록.
  식 안의 `{키}` 는 고른 값(숫자나 글자 모양)으로, `{키:글}` 은 따옴표 없는 글로, `{@설정키}` 는 이 카드의 설정 값(글)으로 바뀐다.
  인자는 `인물칸`, `값선택칸`, `기타후보칸`, `질문인물칸`, `질문답칸`, `대상칸` 으로 만든다.

식은 이렇게 진행단계를 만드는 쪽에만 있고, 작품 제작자는 여기서 정한 항목을 고르기만 한다.
"""
import re
from typing import Any

from .script import Ref, ScriptError, VM, compile_source

MAX_SETTINGS = 50
MAX_CONDITIONS = 100
MAX_ARGS = 6
MAX_CHOICES = 100
MAX_TEXT = 300

SETTING_BUILDERS = ("숫자칸", "선택칸", "켜짐칸", "글칸", "여러선택칸", "서사칸", "후보칸", "질문칸")
ARG_BUILDERS = ("인물칸", "값선택칸", "기타후보칸", "질문인물칸", "질문답칸", "대상칸")
BUILDER_NAMES = frozenset((*SETTING_BUILDERS, *ARG_BUILDERS, "조건항목"))
ENTRY_FUNCTIONS = ("설정정의", "조건정의")
PLACEHOLDER = re.compile(r"\{(@?)([^{}:]+)(?::글)?\}")


def _text(value: Any, what: str, *, required: bool = True) -> str:
    if value is None or value == "":
        if required:
            raise ScriptError(f"{what}을(를) 적어 주세요")
        return ""
    if not isinstance(value, str) or len(value) > MAX_TEXT:
        raise ScriptError(f"{what}은(는) {MAX_TEXT}자 이하의 글이어야 합니다")
    return value


def _key(value: Any) -> str:
    key = _text(value, "키")
    if ":" in key or "{" in key or "}" in key:
        raise ScriptError("키에는 ':' 와 중괄호를 쓸 수 없습니다")
    return key


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _choices(raw: Any) -> list[list[Any]]:
    """선택지: 글 목록이거나 [값, 표시] 쌍의 목록. 항상 [값, 표시] 쌍으로 돌려준다."""
    if not isinstance(raw, (list, tuple)) or not raw or len(raw) > MAX_CHOICES:
        raise ScriptError(f"선택지는 1개 이상 {MAX_CHOICES}개 이하의 목록이어야 합니다")
    out: list[list[Any]] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            value, label = item
        else:
            value = label = item
        if not (isinstance(value, str) or _is_int(value)):
            raise ScriptError("선택지의 값은 글이나 정수여야 합니다")
        out.append([value, _text(label if isinstance(label, str) else str(label), "선택지 이름")])
    if len({v for v, _ in out}) != len(out):
        raise ScriptError("선택지의 값이 겹칩니다")
    return out


def 숫자칸(키: Any, 이름: Any, 기본: Any, 최소: Any = 0, 설명: Any = "") -> dict[str, Any]:
    if not _is_int(기본) or not _is_int(최소) or 기본 < 최소:
        raise ScriptError("숫자칸의 기본값과 최소값은 정수여야 하고 기본값이 최소값 이상이어야 합니다")
    return {"키": _key(키), "이름": _text(이름, "이름"), "종류": "숫자", "기본": 기본, "최소": 최소, "설명": _text(설명, "설명", required=False)}


def 선택칸(키: Any, 이름: Any, 선택지: Any, 기본: Any = None, 설명: Any = "") -> dict[str, Any]:
    choices = _choices(선택지)
    default = choices[0][0] if 기본 is None else 기본
    if default not in [v for v, _ in choices]:
        raise ScriptError("선택칸의 기본값이 선택지에 없습니다")
    return {"키": _key(키), "이름": _text(이름, "이름"), "종류": "선택", "기본": default, "선택": choices, "설명": _text(설명, "설명", required=False)}


def 켜짐칸(키: Any, 이름: Any, 기본: Any = True, 설명: Any = "") -> dict[str, Any]:
    if not isinstance(기본, bool):
        raise ScriptError("켜짐칸의 기본값은 True/False 여야 합니다")
    return {"키": _key(키), "이름": _text(이름, "이름"), "종류": "켜짐", "기본": 기본, "설명": _text(설명, "설명", required=False)}


def 글칸(키: Any, 이름: Any, 기본: Any = "", 설명: Any = "") -> dict[str, Any]:
    return {"키": _key(키), "이름": _text(이름, "이름"), "종류": "글", "기본": _text(기본, "기본값", required=False), "설명": _text(설명, "설명", required=False)}


def 여러선택칸(키: Any, 이름: Any, 선택지: Any, 기본: Any, 설명: Any = "") -> dict[str, Any]:
    choices = _choices(선택지)
    values = [v for v, _ in choices]
    if not isinstance(기본, (list, tuple)) or not 기본 or any(d not in values for d in 기본):
        raise ScriptError("여러선택칸의 기본값은 선택지 중에서 하나 이상이어야 합니다")
    return {"키": _key(키), "이름": _text(이름, "이름"), "종류": "여러선택", "기본": list(기본), "선택": choices, "설명": _text(설명, "설명", required=False)}


def 서사칸(키: Any = "개인서사공개") -> dict[str, Any]:
    """인물마다 보여 줄 서사 부분을 고르는 칸(설정 값 {"인물 순서": [서사 번호, …]})."""
    return {"키": _key(키), "이름": "개인 서사 공개", "종류": "서사", "설명": ""}


def 후보칸(키: Any = "후보") -> dict[str, Any]:
    """투표 후보(인물과 사고사·자살 같은 글)를 고르는 칸(설정 값 [인물 순서 또는 글, …])."""
    return {"키": _key(키), "이름": "투표 후보", "종류": "후보", "설명": ""}


def 질문칸(키: Any = "질문") -> dict[str, Any]:
    """인물마다 다른 질문과 선택지를 적는 칸(설정 값 {"인물 순서": 질문 또는 {질문, 선택}})."""
    return {"키": _key(키), "이름": "개인 질문", "종류": "질문", "설명": ""}


def 인물칸(키: Any, 이름: Any) -> dict[str, Any]:
    return {"키": _key(키), "이름": _text(이름, "이름"), "종류": "인물"}


def 값선택칸(키: Any, 이름: Any, 선택지: Any) -> dict[str, Any]:
    return {"키": _key(키), "이름": _text(이름, "이름"), "종류": "선택", "선택": _choices(선택지)}


def 기타후보칸(키: Any, 이름: Any, 설정: Any = "후보") -> dict[str, Any]:
    """카드 설정 `후보` 에 적힌 글 후보(사고사 등) 중에서 고른다."""
    return {"키": _key(키), "이름": _text(이름, "이름"), "종류": "기타후보", "설정": _key(설정)}


def 질문인물칸(키: Any, 이름: Any, 설정: Any = "질문") -> dict[str, Any]:
    """카드 설정 `질문` 에서 질문이 있는 인물 중에서 고른다."""
    return {"키": _key(키), "이름": _text(이름, "이름"), "종류": "질문인물", "설정": _key(설정)}


def 질문답칸(키: Any, 이름: Any, 인물: Any = "인물", 설정: Any = "질문") -> dict[str, Any]:
    """고른 인물의 질문에 정해 둔 선택지 중에서 고른다. `인물` 은 같은 조건에서 앞서 만든 질문인물칸의 키이다."""
    return {"키": _key(키), "이름": _text(이름, "이름"), "종류": "질문답", "인물": _key(인물), "설정": _key(설정)}


def 대상칸(키: Any, 이름: Any, 설정: Any = "대상") -> dict[str, Any]:
    """능력으로 지목한 대상(인물·장소·단서, 쓰지 않음). 고를 수 있는 종류는 카드 설정 `대상` 이 정한다."""
    return {"키": _key(키), "이름": _text(이름, "이름"), "종류": "대상", "설정": _key(설정)}


def 조건항목(이름: Any, 식: Any, 인자: Any = None) -> dict[str, Any]:
    args = [] if 인자 is None else 인자
    if not isinstance(args, (list, tuple)) or len(args) > MAX_ARGS or not all(isinstance(a, dict) and "종류" in a for a in args):
        raise ScriptError(f"조건항목의 인자는 인물칸() 같은 칸의 목록(최대 {MAX_ARGS}개)이어야 합니다")
    expression = _text(식, "식")
    keys = [a["키"] for a in args]
    if len(set(keys)) != len(keys):
        raise ScriptError("조건항목의 인자 키가 겹칩니다")
    for at, key in ((m.group(1), m.group(2)) for m in PLACEHOLDER.finditer(expression)):
        if not at and key not in keys:
            raise ScriptError(f"식의 {{{key}}} 에 해당하는 인자가 없습니다")
    return {"이름": _text(이름, "이름"), "식": expression, "인자": [dict(a) for a in args]}


DECL_FUNCTIONS = {name: globals()[name] for name in BUILDER_NAMES}


class _DeclHost:
    """선언 함수를 돌릴 때의 호스트: 만드는 함수들만 있고 게임 쪽 대상은 만질 수 없다."""

    constants = {"통과": True}

    def __init__(self) -> None:
        self.functions = dict(DECL_FUNCTIONS)

    def getattr(self, ref: Ref, name: str) -> Any:
        raise ScriptError("설정정의·조건정의 안에서는 게임 대상을 읽을 수 없습니다")

    def method(self, ref: Ref, name: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
        raise ScriptError("설정정의·조건정의 안에서는 게임 대상을 쓸 수 없습니다")


def declarations(source: str, known_names: set[str] | frozenset[str]) -> dict[str, list[dict[str, Any]]] | None:
    """스크립트가 정한 제작 화면. 두 함수가 모두 없으면 None(옛 방식: 스크립트가 글자로 가리키는 설정만 보인다).

    스크립트에 문제가 있으면 `ScriptError`. 한쪽만 있으면 다른 쪽은 빈 목록이다."""
    program = compile_source(source, known_names)
    if not any(f in program.funcs for f in ENTRY_FUNCTIONS):
        return None
    out: dict[str, list[dict[str, Any]]] = {"설정": [], "조건": []}
    for func, key, limit in (("설정정의", "설정", MAX_SETTINGS), ("조건정의", "조건", MAX_CONDITIONS)):
        if func not in program.funcs:
            continue
        vm = VM(program, _DeclHost())
        params = program.funcs[func].params
        vm.start(func, [None] * len(params))
        if vm.run() != "done":
            raise ScriptError(f"{func} 은(는) 입력을 기다릴 수 없습니다")
        result = vm.result
        if not isinstance(result, list) or len(result) > limit or not all(isinstance(r, dict) for r in result):
            raise ScriptError(f"{func} 은(는) {limit}개 이하의 목록을 돌려줘야 합니다")
        out[key] = result
    keys = [s["키"] for s in out["설정"]]
    if len(set(keys)) != len(keys):
        raise ScriptError("설정정의의 키가 겹칩니다")
    for item in out["설정"]:
        if "종류" not in item or "키" not in item:
            raise ScriptError("설정정의는 숫자칸() 같은 칸의 목록을 돌려줘야 합니다")
    names = [c["이름"] for c in out["조건"] if "식" in c]
    if len(out["조건"]) != len(names) or len(set(names)) != len(names):
        raise ScriptError("조건정의는 이름이 겹치지 않는 조건항목() 의 목록을 돌려줘야 합니다")
    for cond in out["조건"]:
        for at, key in ((m.group(1), m.group(2)) for m in PLACEHOLDER.finditer(cond["식"])):
            if at and key not in keys:
                raise ScriptError(f"조건 '{cond['이름']}' 의 {{@{key}}} 에 해당하는 설정 칸이 없습니다")
    return out
