"""스크립트 해석기: 검사, 실행, 입력 대기와 재개, 안전 (docs/ENGINE_DESIGN.md 1-4·1-9)."""
import pytest

from app.script import VM, Ref, ScriptError, Suspend, builtin_names, compile_source


class Host:
    """시험용 호스트: 출력 함수, 입력 대기 함수, Ref 대상의 읽기·메서드."""

    def __init__(self):
        self.out = []
        self.constants = {"통과": True}
        self.functions = {"출력": self.show, "기다리기": self.wait, "사람": lambda: Ref("플레이어", 7)}

    def show(self, value):
        self.out.append(value)

    def wait(self, kind):
        raise Suspend({"종류": kind})

    def getattr(self, ref, name):
        if name == "이름":
            return f"{ref.kind}{ref.key}"
        raise ScriptError(f"'{name}'를 읽을 수 없습니다")

    def method(self, ref, name, args, kwargs):
        self.out.append((ref.kind, name, tuple(args), dict(kwargs)))
        return len(args)


NAMES = set(Host().functions) | {"통과"} | builtin_names()


def run(source, func="실행", args=None, host=None):
    host = host or Host()
    vm = VM(compile_source(source, NAMES), host)
    vm.start(func, args)
    vm.run()
    return vm, host


# ---- 실행 ------------------------------------------------------------------------------------

def test_arithmetic_strings_and_f_strings():
    vm, h = run('''
def 실행():
    a = 7
    b = a // 2 + a % 3 * 2 - 1
    출력(b)
    출력(f"값은 {a}, {b}!")
    출력("가" + "나")
    출력(10 / 4)
''')
    assert vm.done and h.out == [4, "값은 7, 4!", "가나", 2.5]


def test_if_elif_else_and_boolean_short_circuit():
    _, h = run('''
def 실행():
    for n in [1, 2, 3, 4]:
        if n == 1:
            출력("일")
        elif n < 3:
            출력("이")
        else:
            출력("많음")
    출력(0 or "기본")
    출력(1 and 2)
    출력(not False)
    출력("예" if 3 > 2 else "아니오")
''')
    assert h.out == ["일", "이", "많음", "많음", "기본", 2, True, "예"]


def test_while_break_continue_and_for():
    _, h = run('''
def 실행():
    i = 0
    while True:
        i += 1
        if i == 2:
            continue
        if i > 4:
            break
        출력(i)
    for x in range(3):
        for y in [10, 20]:
            if y == 20:
                break
            출력(x * y)
''')
    assert h.out == [1, 3, 4, 0, 10, 20]


def test_lists_dicts_subscripts_and_methods():
    _, h = run('''
def 실행():
    목록 = [3, 1, 2]
    목록.append(5)
    목록[0] = 9
    사전 = {"가": 1, "나": 2}
    사전["다"] = 3
    출력(sorted(목록))
    출력(len(사전))
    출력(사전.get("가", 0))
    출력(사전.get("없음", 0))
    출력(사전.items())
    출력(사전.가)
    출력(", ".join(["가", "나"]))
    출력(2 in 목록)
    출력("라" not in 사전)
''')
    assert h.out == [[1, 2, 5, 9], 3, 1, 0, [("가", 1), ("나", 2), ("다", 3)], 1, "가, 나", True, True]


def test_function_calls_defaults_keywords_and_recursion():
    vm, h = run('''
def 더하기(a, b=10):
    return a + b

def 팩토리얼(n):
    if n <= 1:
        return 1
    return n * 팩토리얼(n - 1)

def 실행():
    출력(더하기(1))
    출력(더하기(1, 2))
    출력(더하기(b=5, a=1))
    출력(팩토리얼(5))
    return 더하기(2, 3)
''')
    assert h.out == [11, 3, 6, 120] and vm.result == 5


def test_refs_attributes_and_methods_go_through_host():
    _, h = run('''
def 실행():
    p = 사람()
    출력(p.이름)
    p.보이기("안녕", 이름="글")
''')
    assert h.out == ["플레이어7", ("플레이어", "보이기", ("안녕",), {"이름": "글"})]


def test_none_is_comparison_and_constants():
    _, h = run('''
def 실행():
    x = None
    출력(x is None)
    출력(x is not None)
    출력(통과)
''')
    assert h.out == [True, False, True]


# ---- 입력 대기와 재개 -------------------------------------------------------------------------

WAIT_SCRIPT = '''
def 도우미():
    return 기다리기("도우미")

def 실행():
    합 = 0
    for n in [1, 2]:
        합 += 기다리기("확인")
        출력(합)
    값 = 도우미()
    출력(f"끝 {값}")
    return 합
'''


def test_script_waits_and_resumes_in_loops_and_nested_calls():
    host = Host()
    vm = VM(compile_source(WAIT_SCRIPT, NAMES), host)
    vm.start("실행")
    assert vm.run() == "waiting" and vm.waiting == {"종류": "확인"}
    vm.resume(10)
    assert vm.run() == "waiting" and host.out == [10]
    vm.resume(5)
    assert vm.run() == "waiting" and vm.waiting == {"종류": "도우미"} and host.out == [10, 15]
    assert len(vm.frames) == 2                                   # 도우미() 안에서 기다리는 중
    vm.resume("끝값")
    assert vm.run() == "done" and vm.done and vm.result == 15 and host.out == [10, 15, "끝 끝값"]


def test_running_while_waiting_stays_waiting_and_resume_requires_waiting():
    host = Host()
    vm = VM(compile_source(WAIT_SCRIPT, NAMES), host)
    vm.start("실행")
    vm.run()
    assert vm.run() == "waiting"                                  # 입력 없이 다시 실행해도 그대로 기다린다
    vm.resume(1)
    vm.run()
    vm.resume(1)
    vm.run()
    vm.resume("x")
    vm.run()
    with pytest.raises(ScriptError):
        vm.resume(1)                                              # 기다리고 있지 않을 때


def test_execution_state_is_plain_data():
    import json

    host = Host()
    vm = VM(compile_source(WAIT_SCRIPT, NAMES), host)
    vm.start("실행")
    vm.run()
    vm.resume(3)
    vm.run()
    state = vm.describe()
    json.dumps(state)                                             # 데이터로 볼 수 있다
    assert state["waiting"] == {"종류": "확인"}
    assert state["frames"][0]["vars"]["합"] == 3 and state["frames"][0]["func"] == "실행"


def test_two_runs_are_independent():
    program = compile_source(WAIT_SCRIPT, NAMES)
    a, b = VM(program, Host()), VM(program, Host())
    a.start("실행")
    b.start("실행")
    a.run()
    b.run()
    a.resume(100)
    a.run()
    assert a.describe()["frames"][0]["vars"]["합"] == 100
    assert "합" in b.describe()["frames"][0]["vars"] and b.describe()["frames"][0]["vars"]["합"] == 0


# ---- 검사 ------------------------------------------------------------------------------------

@pytest.mark.parametrize("source, message", [
    ("def 실행(:\n    pass", "문법 오류"),
    ("x = 1", "함수(def) 밖"),
    ("import os\ndef 실행():\n    pass", "함수(def) 밖"),
    ("def 실행():\n    import os", "Import"),
    ("class A:\n    pass", "함수(def) 밖"),
    ("def 실행():\n    f = lambda: 1", "lambda"),
    ("def 실행():\n    x = [i for i in [1]]", "내포"),
    ("def 실행():\n    try:\n        pass\n    except:\n        pass", "Try"),
    ("def 실행():\n    with 사람() as p:\n        pass", "With"),
    ("def 실행():\n    global x", "Global"),
    ("def 실행():\n    del x", "Delete"),
    ("def 실행():\n    yield 1", "yield"),
    ("def 실행():\n    x = 사람().__class__", "밑줄"),
    ("def 실행():\n    __import__('os')", "밑줄"),
    ("def 실행():\n    _x = 1", "밑줄"),
    ("def 실행():\n    x = 2 ** 3", "산술 기호"),
    ("def 실행():\n    x = [1][0:1]", "슬라이스"),
    ("def 실행():\n    x = 1 < 2 < 3", "한 번에 하나"),
    ("def 실행():\n    x = 몰라", "알 수 없는 이름"),
    ("def 실행():\n    몰라()", "알 수 없는 이름"),
    ("def 실행():\n    (lambda: 1)()", "호출할 수 있습니다"),
    ("def 실행():\n    사람()()", "호출할 수 있습니다"),
    ("def 실행():\n    break", "반복문 안"),
    ("def 실행():\n    a, b = 1, 2", "이름이나 a[i]"),
    ("def 실행():\n    a = b = 1", "여러 이름"),
    ("def 실행(*a):\n    pass", "*인자"),
    ("@x\ndef 실행():\n    pass", "데코레이터"),
    ("def 실행(a=사람()):\n    pass", "기본값"),
    ("def 실행():\n    출력(**{})", "**"),
    ("def f():\n    pass\ndef f():\n    pass", "두 번"),
    ("def 실행():\n    x = {1, 2}", "Set"),
    ("def 실행():\n    x = 1\n    x.y = 2", "이름이나 a[i]"),
])
def test_compile_rejects(source, message):
    with pytest.raises(ScriptError) as err:
        compile_source(source, NAMES)
    assert message in str(err.value)


def test_error_reports_line_number():
    with pytest.raises(ScriptError) as err:
        compile_source("def 실행():\n    출력(1)\n    몰라()", NAMES)
    assert err.value.line == 3 and "3번째 줄" in str(err.value)


# ---- 실행 중 오류와 안전 ------------------------------------------------------------------------

def test_runtime_errors_are_script_errors_with_lines():
    for body, message in [
        ("x = 1 / 0", "실행 중 오류"),
        ("x = [1][5]", "실행 중 오류"),
        ("x = 사람().없음", "읽을 수 없습니다"),
        ("x = 1 + '가'", "+ 는"),
        ("x = '가' < 1", "비교"),
        ("x = len(3)", "실행 중 오류"),
        ("x = {}.없음", "항목이 없습니다"),
        ("x = (1).foo()", "메서드"),
    ]:
        with pytest.raises(ScriptError) as err:
            run(f"def 실행():\n    {body}")
        assert message in str(err.value) and err.value.line == 2, (body, str(err.value))


def test_infinite_loop_is_stopped():
    with pytest.raises(ScriptError) as err:
        run("def 실행():\n    while True:\n        pass")
    assert "너무 오래" in str(err.value)


def test_runaway_recursion_is_stopped():
    with pytest.raises(ScriptError) as err:
        run("def 다시():\n    다시()\n\ndef 실행():\n    다시()")
    assert "너무 깊게" in str(err.value)


def test_huge_ranges_and_repeats_are_stopped():
    for body in ["x = range(10 ** 9)", "x = 'ab' * 100000"]:
        if "10 **" in body:
            with pytest.raises(ScriptError):
                compile_source(f"def 실행():\n    {body}", NAMES)         # ** 는 허용하지 않는다
            continue
        with pytest.raises(ScriptError):
            run(f"def 실행():\n    {body}")
    with pytest.raises(ScriptError) as err:
        run("def 실행():\n    x = range(1000000)")
    assert "range" in str(err.value)


def test_scripts_cannot_reach_python_internals():
    # 호스트가 주지 않은 이름은 쓸 수 없고, 값에서 파이썬 내부로 나가는 길(속성·메서드)도 없다.
    for body in ["x = open('f')", "x = eval('1')", "x = getattr(1, 'a')", "x = __builtins__"]:
        with pytest.raises(ScriptError):
            run(f"def 실행():\n    {body}")
    with pytest.raises(ScriptError):
        run("def 실행():\n    x = 'a'.upper()")
    with pytest.raises(ScriptError):
        run("def 실행():\n    x = [].sort()")


def test_host_call_with_wrong_arguments_explains_the_usage():
    host = Host()
    host.functions["글"] = lambda 이름, 내용: (이름, 내용)
    program = compile_source("def 실행():\n    return 글('안녕')", {"글"})
    vm = VM(program, host)
    vm.start("실행", [])
    with pytest.raises(ScriptError) as err:
        vm.run()
    assert "사용법: 글(이름, 내용)" in str(err.value) and "2번째 줄" in str(err.value)
