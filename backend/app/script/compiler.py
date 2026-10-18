"""스크립트 검사와 번역: 파이썬 문법으로 쓴 글을 읽어 허용한 것만 통과시키고, 단계별로 실행할 수 있는 명령 목록으로 바꾼다.

허용하는 것
  * 최상위에는 `def` 만 쓴다(데코레이터·`*args`·`**kwargs`·기본값이 상수가 아닌 것은 안 된다).
  * 문장: 대입(이름·`a[i]`), `+=` 같은 누적 대입, `if/elif/else`, `while`, `for 이름 in 목록`, `break`, `continue`, `return`, `pass`, 식 문장.
  * 식: 상수, 이름, `a.b`(읽기), 호출(`이름(...)`, `대상.메서드(...)`, 이름 붙인 인자 포함), 산술(`+ - * / // %`), 비교(한 번에 하나),
    `and`/`or`/`not`, `x if c else y`, 목록·튜플·사전, `a[i]`, f-문자열.
허용하지 않는 것: `import`, `class`, `lambda`, `try`, `with`, `global`, `del`, `yield`, `await`, 내포(`[... for ...]`), 슬라이스, `**`, 밑줄로 시작하는 이름,
  이름 없는 함수 호출(`f()()`) 등. 모르는 이름은 저장할 때 알려 준다.
"""
import ast
from dataclasses import dataclass, field
from typing import Any
from ..josa import attach, quoted

# 명령 목록의 한 칸: (명령, 인자, 줄 번호)
Instr = tuple[str, Any, int]


class ScriptError(Exception):
    """스크립트의 오류. 제작자에게 보여 줄 한국어 메시지와 줄 번호를 가진다."""

    def __init__(self, message: str, line: int | None = None):
        super().__init__(message)
        self.message, self.line = message, line

    def __str__(self) -> str:
        return f"{self.line}번째 줄: {self.message}" if self.line else self.message


@dataclass
class Func:
    name: str
    params: list[str]
    defaults: dict[str, Any]
    code: list[Instr] = field(default_factory=list)


@dataclass
class Program:
    funcs: dict[str, Func]


BINOPS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//", ast.Mod: "%"}
CMPOPS = {
    ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
    ast.In: "in", ast.NotIn: "not in", ast.Is: "is", ast.IsNot: "is not",
}
CONSTANT_TYPES = (str, int, float, bool, type(None))


def _line(node: ast.AST) -> int:
    return getattr(node, "lineno", 0)


def _reject(node: ast.AST, what: str) -> ScriptError:
    return ScriptError(f"{attach(what, '은/는')} 쓸 수 없습니다", _line(node))


def compile_expression(expression: str, known_names: set[str] | frozenset[str] = frozenset()) -> Program:
    """한 줄(또는 여러 줄) 식을 `조건()` 함수 하나짜리 프로그램으로 번역한다. 엔딩·후일담의 조건에 쓴다.

    식 하나만 받는다(여러 문장이나 정의를 끼워 넣을 수 없다). 오류의 줄 번호는 식의 줄 기준이다.
    """
    text = (expression or "").strip()
    if not text:
        raise ScriptError("식이 비어 있습니다")
    try:
        ast.parse(text, mode="eval")
    except SyntaxError as err:
        raise ScriptError(f"문법 오류: {err.msg}", err.lineno) from None
    except ValueError as err:
        raise ScriptError(f"읽을 수 없는 글입니다: {err}") from None
    try:
        return compile_source(f"def 조건():\n    return (\n{text}\n)\n", known_names)
    except ScriptError as err:
        if err.line is not None:
            err.line = max(err.line - 2, 1)
        raise


def compile_source(source: str, known_names: set[str] | frozenset[str] = frozenset()) -> Program:
    """스크립트를 검사하고 번역한다. 문제가 있으면 `ScriptError`. `known_names` 는 호출할 수 있는 기본 함수·상수의 이름이다."""
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as err:
        raise ScriptError(f"문법 오류: {err.msg}", err.lineno) from None
    except ValueError as err:
        raise ScriptError(f"읽을 수 없는 글입니다: {err}") from None

    defs: list[ast.FunctionDef] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            defs.append(node)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue                                         # 맨 위의 설명 글
        else:
            raise ScriptError("함수(def) 밖에는 아무것도 쓸 수 없습니다", _line(node))
    names = [d.name for d in defs]
    for d in defs:
        if d.name.startswith("_"):
            raise ScriptError("함수 이름은 밑줄로 시작할 수 없습니다", _line(d))
        if names.count(d.name) > 1:
            raise ScriptError(f"함수 {quoted(d.name, '이/가')} 두 번 정의되었습니다", _line(d))
    visible = set(known_names) | set(names)
    return Program({d.name: _FunctionCompiler(d, visible).compile() for d in defs})


class _FunctionCompiler:
    def __init__(self, node: ast.FunctionDef, visible: set[str]):
        self.node, self.visible = node, visible
        self.code: list[Instr] = []
        self.loops: list[dict[str, list[int]]] = []     # 반복문마다 break·continue 가 채울 자리
        self.hidden = 0
        a = node.args
        if node.decorator_list:
            raise _reject(node, "데코레이터")
        if a.vararg or a.kwarg or a.kwonlyargs or a.posonlyargs:
            raise _reject(node, "*인자·**인자·키워드 전용 인자")
        self.params = [p.arg for p in a.args]
        defaults: dict[str, Any] = {}
        for param, default in zip(reversed(a.args), reversed(a.defaults)):
            if not (isinstance(default, ast.Constant) and isinstance(default.value, CONSTANT_TYPES)):
                raise ScriptError("인자의 기본값은 글자·숫자·참/거짓·None 만 쓸 수 있습니다", _line(default))
            defaults[param.arg] = default.value
        self.defaults = defaults
        self.assigned = set(self.params) | self._collect_assigned(node.body)
        for name in self.assigned:
            if name.startswith("_"):
                raise ScriptError(f"이름 {quoted(name, '은/는')} 밑줄로 시작할 수 없습니다", _line(node))

    # ---- 준비 --------------------------------------------------------------------------
    def _collect_assigned(self, body: list[ast.stmt]) -> set[str]:
        out: set[str] = set()
        for stmt in body:
            for node in ast.walk(stmt):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    out.add(node.id)
        return out

    def compile(self) -> Func:
        self.block(self.node.body)
        self.emit("LOAD_CONST", None, self.node)
        self.emit("RETURN", None, self.node)
        return Func(self.node.name, self.params, self.defaults, self.code)

    def emit(self, op: str, arg: Any, node: ast.AST) -> int:
        self.code.append((op, arg, _line(node)))
        return len(self.code) - 1

    def patch(self, at: int, target: int) -> None:
        """건너뛸 곳(`JUMP*`, `FOR_ITER`)의 도착 위치를 채운다."""
        op, arg, line = self.code[at]
        arg = (arg[0], arg[1], target) if op == "FOR_ITER" else target
        self.code[at] = (op, arg, line)

    def here(self) -> int:
        return len(self.code)

    # ---- 문장 --------------------------------------------------------------------------
    def block(self, body: list[ast.stmt]) -> None:
        for stmt in body:
            self.stmt(stmt)

    def stmt(self, node: ast.stmt) -> None:
        if isinstance(node, ast.Expr):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return                                        # 설명 글
            self.expr(node.value)
            self.emit("POP", None, node)
        elif isinstance(node, ast.Assign):
            if len(node.targets) != 1:
                raise _reject(node, "여러 이름에 한 번에 대입")
            self.assign(node.targets[0], node.value, node)
        elif isinstance(node, ast.AugAssign):
            target = node.target
            if not isinstance(target, ast.Name) or type(node.op) not in BINOPS:
                raise _reject(node, "이름이 아닌 곳의 누적 대입")
            self.name_load(target)
            self.expr(node.value)
            self.emit("BINARY", BINOPS[type(node.op)], node)
            self.emit("STORE_NAME", target.id, node)
        elif isinstance(node, ast.If):
            self.expr(node.test)
            skip = self.emit("JUMP_IF_FALSE", None, node)
            self.block(node.body)
            if node.orelse:
                over = self.emit("JUMP", None, node)
                self.patch(skip, self.here())
                self.block(node.orelse)
                self.patch(over, self.here())
            else:
                self.patch(skip, self.here())
        elif isinstance(node, ast.While):
            if node.orelse:
                raise _reject(node, "while 의 else")
            start = self.here()
            self.expr(node.test)
            leave = self.emit("JUMP_IF_FALSE", None, node)
            self.loops.append({"break": [], "continue": []})
            self.block(node.body)
            ctx = self.loops.pop()
            self.emit("JUMP", start, node)
            end = self.here()
            self.patch(leave, end)
            for at in ctx["break"]:
                self.patch(at, end)
            for at in ctx["continue"]:
                self.patch(at, start)
        elif isinstance(node, ast.For):
            if node.orelse or not isinstance(node.target, ast.Name):
                raise _reject(node, "이름 하나가 아닌 for 대상이나 for 의 else")
            hidden = f"$it{self.hidden}"
            self.hidden += 1
            self.expr(node.iter)
            self.emit("GET_ITER", hidden, node)
            start = self.here()
            step = self.emit("FOR_ITER", (hidden, node.target.id, None), node)
            self.loops.append({"break": [], "continue": []})
            self.block(node.body)
            ctx = self.loops.pop()
            self.emit("JUMP", start, node)
            end = self.here()
            self.patch(step, end)
            for at in ctx["break"]:
                self.patch(at, end)
            for at in ctx["continue"]:
                self.patch(at, start)
        elif isinstance(node, ast.Break):
            if not self.loops:
                raise ScriptError("break 는 반복문 안에서만 쓸 수 있습니다", _line(node))
            self.loops[-1]["break"].append(self.emit("JUMP", None, node))
        elif isinstance(node, ast.Continue):
            if not self.loops:
                raise ScriptError("continue 는 반복문 안에서만 쓸 수 있습니다", _line(node))
            self.loops[-1]["continue"].append(self.emit("JUMP", None, node))
        elif isinstance(node, ast.Return):
            if node.value is None:
                self.emit("LOAD_CONST", None, node)
            else:
                self.expr(node.value)
            self.emit("RETURN", None, node)
        elif isinstance(node, ast.Pass):
            return
        else:
            raise _reject(node, type(node).__name__)

    def assign(self, target: ast.expr, value: ast.expr, node: ast.stmt) -> None:
        if isinstance(target, ast.Name):
            self.expr(value)
            self.emit("STORE_NAME", target.id, node)
        elif isinstance(target, ast.Subscript) and not isinstance(target.slice, ast.Slice):
            self.expr(target.value)
            self.expr(target.slice)
            self.expr(value)
            self.emit("STORE_SUBSCR", None, node)
        else:
            raise _reject(node, "이름이나 a[i] 가 아닌 곳에 대입")

    # ---- 식 ----------------------------------------------------------------------------
    def name_load(self, node: ast.Name) -> None:
        if node.id.startswith("_"):
            raise ScriptError(f"이름 {quoted(node.id, '은/는')} 밑줄로 시작할 수 없습니다", _line(node))
        if node.id not in self.assigned and node.id not in self.visible:
            raise ScriptError(f"알 수 없는 이름 '{node.id}'", _line(node))
        self.emit("LOAD_NAME", node.id, node)

    def expr(self, node: ast.expr) -> None:
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, CONSTANT_TYPES):
                raise _reject(node, "이런 종류의 상수")
            self.emit("LOAD_CONST", node.value, node)
        elif isinstance(node, ast.Name):
            self.name_load(node)
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise ScriptError(f"{quoted(node.attr, '은/는')} 밑줄로 시작해서 쓸 수 없습니다", _line(node))
            self.expr(node.value)
            self.emit("LOAD_ATTR", node.attr, node)
        elif isinstance(node, ast.Call):
            self.call(node)
        elif isinstance(node, ast.BinOp):
            if type(node.op) not in BINOPS:
                raise _reject(node, "이 산술 기호")
            self.expr(node.left)
            self.expr(node.right)
            self.emit("BINARY", BINOPS[type(node.op)], node)
        elif isinstance(node, ast.UnaryOp):
            ops = {ast.Not: "not", ast.USub: "-", ast.UAdd: "+"}
            if type(node.op) not in ops:
                raise _reject(node, "이 기호")
            self.expr(node.operand)
            self.emit("UNARY", ops[type(node.op)], node)
        elif isinstance(node, ast.Compare):
            if len(node.ops) != 1:
                raise ScriptError("비교는 한 번에 하나만 쓸 수 있습니다(예: 0 < x < 5 대신 0 < x and x < 5)", _line(node))
            self.expr(node.left)
            self.expr(node.comparators[0])
            self.emit("COMPARE", CMPOPS[type(node.ops[0])], node)
        elif isinstance(node, ast.BoolOp):
            op = "JUMP_IF_FALSE_OR_POP" if isinstance(node.op, ast.And) else "JUMP_IF_TRUE_OR_POP"
            jumps = []
            for value in node.values[:-1]:
                self.expr(value)
                jumps.append(self.emit(op, None, node))
            self.expr(node.values[-1])
            for at in jumps:
                self.patch(at, self.here())
        elif isinstance(node, ast.IfExp):
            self.expr(node.test)
            other = self.emit("JUMP_IF_FALSE", None, node)
            self.expr(node.body)
            over = self.emit("JUMP", None, node)
            self.patch(other, self.here())
            self.expr(node.orelse)
            self.patch(over, self.here())
        elif isinstance(node, (ast.List, ast.Tuple)):
            for item in node.elts:
                if isinstance(item, ast.Starred):
                    raise _reject(item, "*목록 펼치기")
                self.expr(item)
            self.emit("BUILD_LIST" if isinstance(node, ast.List) else "BUILD_TUPLE", len(node.elts), node)
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if key is None:
                    raise _reject(node, "**사전 펼치기")
                self.expr(key)
                self.expr(value)
            self.emit("BUILD_DICT", len(node.keys), node)
        elif isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Slice):
                raise _reject(node, "슬라이스(a[1:2])")
            self.expr(node.value)
            self.expr(node.slice)
            self.emit("SUBSCR", None, node)
        elif isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.Constant):
                    self.emit("LOAD_CONST", str(part.value), part)
                elif isinstance(part, ast.FormattedValue):
                    if part.format_spec is not None or part.conversion != -1:
                        raise _reject(part, "f-문자열의 형식 지정")
                    self.expr(part.value)
                    self.emit("TO_STR", None, part)
                else:
                    raise _reject(part, "이런 f-문자열")
            self.emit("BUILD_STRING", len(node.values), node)
        else:
            raise _reject(node, {"Lambda": "lambda", "ListComp": "내포(목록 만들기 한 줄 식)", "GeneratorExp": "내포",
                                 "DictComp": "내포", "SetComp": "내포", "Await": "await", "Yield": "yield",
                                 "NamedExpr": ":="}.get(type(node).__name__, type(node).__name__))

    def call(self, node: ast.Call) -> None:
        kwnames: list[str] = []
        for kw in node.keywords:
            if kw.arg is None:
                raise _reject(node, "**인자 펼치기")
        func = node.func
        if isinstance(func, ast.Name):
            if func.id.startswith("_"):
                raise ScriptError(f"이름 {quoted(func.id, '은/는')} 밑줄로 시작할 수 없습니다", _line(func))
            if func.id not in self.assigned and func.id not in self.visible:
                raise ScriptError(f"알 수 없는 이름 '{func.id}'", _line(func))
            target: Any = ("name", func.id)
        elif isinstance(func, ast.Attribute):
            if func.attr.startswith("_"):
                raise ScriptError(f"{quoted(func.attr, '은/는')} 밑줄로 시작해서 쓸 수 없습니다", _line(func))
            self.expr(func.value)
            target = ("method", func.attr)
        else:
            raise ScriptError("함수 이름이나 대상.메서드 만 호출할 수 있습니다", _line(node))
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                raise _reject(arg, "*인자 펼치기")
            self.expr(arg)
        for kw in node.keywords:
            kwnames.append(kw.arg)
            self.expr(kw.value)
        self.emit("CALL", (target[0], target[1], len(node.args), tuple(kwnames)), node)
