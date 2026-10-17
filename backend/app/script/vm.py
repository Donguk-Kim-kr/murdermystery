"""스크립트 실행기: 번역된 명령 목록을 한 단계씩 실행한다.

실행 상태(함수 호출 구조, 각 호출의 위치·값 더미·변수)는 모두 데이터로 들고 있다(`VM.frames`). 입력을 기다리는 함수를 만나면
(`Suspend`) 그 자리에서 멈추고, 입력이 오면 `resume(값)` 으로 이어서 실행한다(docs/ENGINE_DESIGN.md 1-9, 선택지 A2).
스크립트가 만지는 게임 쪽 대상(플레이어, 인물, 카드 등)은 `Ref` 로만 다룬다. 그 대상에 하는 일은 모두 `host` 가 정한다.
"""
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .compiler import Program, ScriptError

MAX_STEPS = 200_000        # 한 번 실행하는 동안 허용하는 명령 수(끝없는 반복을 막는다)
MAX_DEPTH = 30             # 함수 호출이 겹칠 수 있는 깊이
MAX_ITEMS = 10_000         # range 나 문자열 곱하기가 만들 수 있는 크기


@dataclass(frozen=True)
class Ref:
    """게임 쪽 대상을 가리키는 값. 예: Ref("플레이어", 계정번호), Ref("인물", 순서), Ref("모두")."""

    kind: str
    key: Any = None

    def describe(self) -> dict[str, Any]:
        return {"kind": self.kind, "key": self.key}


class Suspend(Exception):
    """호스트 함수가 일으켜서 스크립트를 멈추게 한다. `descriptor` 는 무엇을 기다리는지 알려 주는 값이다."""

    def __init__(self, descriptor: dict[str, Any]):
        super().__init__("waiting")
        self.descriptor = descriptor


class Host(Protocol):
    functions: dict[str, Callable[..., Any]]
    constants: dict[str, Any]

    def getattr(self, ref: Ref, name: str) -> Any: ...
    def method(self, ref: Ref, name: str, args: list[Any], kwargs: dict[str, Any]) -> Any: ...


@dataclass
class Frame:
    func: str
    pc: int = 0
    stack: list[Any] = field(default_factory=list)
    vars: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Iter:
    items: list[Any]
    index: int = 0


def _builtin_range(*args: int) -> list[int]:
    result = range(*args)
    if len(result) > MAX_ITEMS:
        raise ScriptError(f"range 는 {MAX_ITEMS}개까지만 만들 수 있습니다")
    return list(result)


BUILTINS: dict[str, Callable[..., Any]] = {
    "len": len, "range": _builtin_range, "str": str, "int": int, "float": float, "bool": bool, "abs": abs,
    "min": min, "max": max, "sum": sum, "sorted": sorted, "list": list, "round": round,
}
CONSTANTS = {"True": True, "False": False, "None": None}


def builtin_names() -> set[str]:
    return set(BUILTINS) | set(CONSTANTS)


class VM:
    """한 스크립트(`Program`)의 한 번의 실행. `start` → `run` → (`waiting` 이면 `resume` → `run`) 을 되풀이한다."""

    def __init__(self, program: Program, host: Host):
        self.program, self.host = program, host
        self.frames: list[Frame] = []
        self.waiting: dict[str, Any] | None = None
        self.done = False
        self.result: Any = None

    # ---- 시작·이어서 실행 ----------------------------------------------------------------
    def start(self, func: str, args: list[Any] | None = None) -> None:
        if func not in self.program.funcs:
            raise ScriptError(f"함수 '{func}' 이(가) 없습니다")
        self.frames = []
        self.done, self.result, self.waiting = False, None, None
        self._push_frame(func, list(args or []), {})

    def resume(self, value: Any) -> None:
        """입력을 기다리던 호출의 결과로 `value` 를 넣는다. 이어서 `run` 을 불러야 실행이 계속된다."""
        if self.waiting is None:
            raise ScriptError("입력을 기다리고 있지 않습니다")
        self.frames[-1].stack.append(value)
        self.waiting = None

    def run(self) -> str:
        """멈출 곳(끝, 입력 대기)까지 실행한다. `done` 이나 `waiting` 을 돌려준다. 오류는 `ScriptError`."""
        if self.waiting is not None:
            return "waiting"
        steps = 0
        while self.frames:
            steps += 1
            if steps > MAX_STEPS:
                raise ScriptError("스크립트가 너무 오래 실행되었습니다(끝나지 않는 반복일 수 있습니다)", self._line())
            frame = self.frames[-1]
            op, arg, line = self.program.funcs[frame.func].code[frame.pc]
            frame.pc += 1
            try:
                status = self._step(frame, op, arg)
            except ScriptError as err:
                if err.line is None:
                    err.line = line
                raise
            except Suspend as sus:
                self.waiting = sus.descriptor
                return "waiting"
            except (TypeError, ValueError, KeyError, IndexError, ZeroDivisionError, AttributeError) as err:
                raise ScriptError(f"실행 중 오류: {err}", line) from None
            if status == "done":
                break
        self.done = True
        return "done"

    # ---- 확인용 --------------------------------------------------------------------------
    def describe(self) -> dict[str, Any]:
        """지금 실행 상태를 JSON 으로 볼 수 있는 값으로 돌려준다(시험·점검용)."""

        def plain(v: Any) -> Any:
            if isinstance(v, Ref):
                return v.describe()
            if isinstance(v, _Iter):
                return {"iter": [plain(x) for x in v.items], "index": v.index}
            if isinstance(v, (list, tuple)):
                return [plain(x) for x in v]
            if isinstance(v, dict):
                return {str(k): plain(x) for k, x in v.items()}
            return v

        return {
            "done": self.done, "waiting": self.waiting,
            "frames": [{"func": f.func, "pc": f.pc, "stack": plain(f.stack), "vars": plain(f.vars)} for f in self.frames],
        }

    # ---- 내부 ----------------------------------------------------------------------------
    def _line(self) -> int | None:
        if not self.frames:
            return None
        f = self.frames[-1]
        code = self.program.funcs[f.func].code
        return code[min(max(f.pc - 1, 0), len(code) - 1)][2]

    def _push_frame(self, name: str, args: list[Any], kwargs: dict[str, Any]) -> None:
        if len(self.frames) >= MAX_DEPTH:
            raise ScriptError("함수 호출이 너무 깊게 겹쳤습니다")
        func = self.program.funcs[name]
        if len(args) > len(func.params):
            raise ScriptError(f"'{name}' 은(는) 인자를 {len(func.params)}개까지만 받습니다")
        values: dict[str, Any] = dict(zip(func.params, args))
        for key, value in kwargs.items():
            if key not in func.params:
                raise ScriptError(f"'{name}' 에는 '{key}' 인자가 없습니다")
            if key in values:
                raise ScriptError(f"'{name}' 의 '{key}' 인자가 두 번 주어졌습니다")
            values[key] = value
        for param in func.params:
            if param not in values:
                if param not in func.defaults:
                    raise ScriptError(f"'{name}' 에 '{param}' 인자가 필요합니다")
                values[param] = func.defaults[param]
        self.frames.append(Frame(name, 0, [], values))

    def _lookup(self, frame: Frame, name: str) -> Any:
        if name in frame.vars:
            return frame.vars[name]
        if name in CONSTANTS:
            return CONSTANTS[name]
        if name in self.host.constants:
            return self.host.constants[name]
        raise ScriptError(f"값이 아직 없는 이름 '{name}' 입니다")

    def _step(self, frame: Frame, op: str, arg: Any) -> str | None:
        stack = frame.stack
        if op == "LOAD_CONST":
            stack.append(arg)
        elif op == "LOAD_NAME":
            stack.append(self._lookup(frame, arg))
        elif op == "STORE_NAME":
            frame.vars[arg] = stack.pop()
        elif op == "POP":
            stack.pop()
        elif op == "LOAD_ATTR":
            stack.append(self._getattr(stack.pop(), arg))
        elif op == "BINARY":
            right, left = stack.pop(), stack.pop()
            stack.append(_binary(arg, left, right))
        elif op == "UNARY":
            value = stack.pop()
            stack.append((not value) if arg == "not" else -value if arg == "-" else +value)
        elif op == "COMPARE":
            right, left = stack.pop(), stack.pop()
            stack.append(_compare(arg, left, right))
        elif op == "JUMP":
            frame.pc = arg
        elif op == "JUMP_IF_FALSE":
            if not stack.pop():
                frame.pc = arg
        elif op == "JUMP_IF_FALSE_OR_POP":
            if not stack[-1]:
                frame.pc = arg
            else:
                stack.pop()
        elif op == "JUMP_IF_TRUE_OR_POP":
            if stack[-1]:
                frame.pc = arg
            else:
                stack.pop()
        elif op == "BUILD_LIST":
            items = stack[len(stack) - arg:] if arg else []
            del stack[len(stack) - arg:]
            stack.append(list(items))
        elif op == "BUILD_TUPLE":
            items = stack[len(stack) - arg:] if arg else []
            del stack[len(stack) - arg:]
            stack.append(tuple(items))
        elif op == "BUILD_DICT":
            items = stack[len(stack) - 2 * arg:] if arg else []
            del stack[len(stack) - 2 * arg:]
            stack.append({items[i]: items[i + 1] for i in range(0, len(items), 2)})
        elif op == "SUBSCR":
            index, base = stack.pop(), stack.pop()
            if isinstance(base, (list, tuple, str, dict)):
                stack.append(base[index])
            else:
                raise ScriptError("[ ] 로 읽을 수 없는 값입니다")
        elif op == "STORE_SUBSCR":
            value, index, base = stack.pop(), stack.pop(), stack.pop()
            if not isinstance(base, (list, dict)):
                raise ScriptError("[ ] 로 바꿀 수 없는 값입니다")
            base[index] = value
        elif op == "TO_STR":
            stack.append(_to_str(stack.pop()))
        elif op == "BUILD_STRING":
            parts = stack[len(stack) - arg:] if arg else []
            del stack[len(stack) - arg:]
            stack.append("".join(parts))
        elif op == "GET_ITER":
            value = stack.pop()
            if isinstance(value, dict):
                items = list(value.keys())
            elif isinstance(value, (list, tuple, str)):
                items = list(value)
            else:
                raise ScriptError("for 로 하나씩 꺼낼 수 없는 값입니다")
            frame.vars[arg] = _Iter(items)
        elif op == "FOR_ITER":
            hidden, name, end = arg
            it: _Iter = frame.vars[hidden]
            if it.index >= len(it.items):
                frame.pc = end
            else:
                frame.vars[name] = it.items[it.index]
                it.index += 1
        elif op == "CALL":
            return self._call(frame, *arg)
        elif op == "RETURN":
            value = stack.pop() if stack else None
            self.frames.pop()
            if self.frames:
                self.frames[-1].stack.append(value)
            else:
                self.result = value
                return "done"
        else:
            raise ScriptError(f"알 수 없는 명령 {op}")
        return None

    def _getattr(self, obj: Any, name: str) -> Any:
        if isinstance(obj, Ref):
            return self.host.getattr(obj, name)
        if isinstance(obj, dict):
            if name in obj:
                return obj[name]
            raise ScriptError(f"'{name}' 항목이 없습니다")
        raise ScriptError(f"'{name}' 을(를) 읽을 수 없는 값입니다")

    def _call(self, frame: Frame, kind: str, name: str, argc: int, kwnames: tuple[str, ...]) -> str | None:
        stack = frame.stack
        total = argc + len(kwnames)
        values = stack[len(stack) - total:] if total else []
        del stack[len(stack) - total:]
        args, kwargs = list(values[:argc]), dict(zip(kwnames, values[argc:]))
        if kind == "method":
            obj = stack.pop()
            stack.append(self._method(obj, name, args, kwargs))
            return None
        if name in self.program.funcs:
            self._push_frame(name, args, kwargs)
            return None
        if name in self.host.functions:
            fn = self.host.functions[name]
            try:
                inspect.signature(fn).bind(*args, **kwargs)
            except TypeError:
                names = ", ".join(inspect.signature(fn).parameters)
                raise ScriptError(f"'{name}' 을(를) 부르는 방법이 맞지 않습니다. 사용법: {name}({names})") from None
            stack.append(fn(*args, **kwargs))
            return None
        if name in BUILTINS:
            if kwargs:
                raise ScriptError(f"'{name}' 은(는) 이름 붙인 인자를 받지 않습니다")
            stack.append(BUILTINS[name](*args))
            return None
        raise ScriptError(f"알 수 없는 함수 '{name}'")

    def _method(self, obj: Any, name: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
        if isinstance(obj, Ref):
            return self.host.method(obj, name, args, kwargs)
        if isinstance(obj, dict) and not kwargs:
            if name == "get":
                return obj.get(*args)
            if name in ("items", "keys", "values") and not args:
                return list(getattr(obj, name)())
        if isinstance(obj, list) and name == "append" and len(args) == 1 and not kwargs:
            obj.append(args[0])
            return None
        if isinstance(obj, str) and name == "join" and len(args) == 1 and not kwargs:
            return obj.join(str(x) for x in args[0])
        raise ScriptError(f"이 값에는 '{name}' 메서드를 쓸 수 없습니다")


def _to_str(value: Any) -> str:
    if isinstance(value, Ref):
        raise ScriptError("대상을 글자로 바꿀 수 없습니다(이름 같은 값을 꺼내서 쓰세요)")
    return str(value)


def _binary(op: str, left: Any, right: Any) -> Any:
    numbers = (int, float)
    if op == "+":
        if isinstance(left, numbers) and isinstance(right, numbers):
            return left + right
        if isinstance(left, str) and isinstance(right, str):
            return left + right
        if isinstance(left, list) and isinstance(right, list):
            return left + right
        raise ScriptError("+ 는 숫자끼리, 글자끼리, 목록끼리만 쓸 수 있습니다")
    if op == "*" and isinstance(left, str) and isinstance(right, int):
        if len(left) * max(right, 0) > MAX_ITEMS:
            raise ScriptError("글자를 너무 많이 반복했습니다")
        return left * right
    if not (isinstance(left, numbers) and isinstance(right, numbers)):
        raise ScriptError(f"{op} 는 숫자끼리만 쓸 수 있습니다")
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    if op == "/":
        return left / right
    if op == "//":
        return left // right
    if op == "%":
        return left % right
    raise ScriptError(f"알 수 없는 산술 기호 {op}")


def _compare(op: str, left: Any, right: Any) -> bool:
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == "is":
        return left is right or (isinstance(left, (bool, type(None))) and type(left) is type(right) and left == right)
    if op == "is not":
        return not _compare("is", left, right)
    if op == "in":
        return left in right
    if op == "not in":
        return left not in right
    if op in ("<", "<=", ">", ">="):
        numbers = (int, float)
        if not ((isinstance(left, numbers) and isinstance(right, numbers)) or (isinstance(left, str) and isinstance(right, str))):
            raise ScriptError(f"{op} 는 숫자끼리나 글자끼리만 비교할 수 있습니다")
        return {"<": left < right, "<=": left <= right, ">": left > right, ">=": left >= right}[op]
    raise ScriptError(f"알 수 없는 비교 기호 {op}")
