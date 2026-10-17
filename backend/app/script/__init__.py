"""제작자가 쓰는 스크립트: 파이썬 문법의 제한된 부분을 읽어(`compiler`) 단계별로 실행하는(`vm`) 해석기.

docs/ENGINE_DESIGN.md 1-4, 1-9 와 docs/ENGINE_SPEC.md 를 따른다. 실제 파이썬(`exec`/`eval`)으로 실행하지 않는다.
허용한 구성 요소만 직접 해석하고, 실행 상태(위치·변수·호출 구조)는 별도의 데이터로 들고 있어서 입력을 기다렸다가 이어서 실행한다.
"""
from .compiler import Program, ScriptError, compile_source
from .vm import VM, Ref, Suspend, builtin_names

__all__ = ["Program", "Ref", "ScriptError", "Suspend", "VM", "builtin_names", "compile_source"]
