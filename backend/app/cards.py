"""카드(진행단계를 페이즈에 놓은 것)의 실행: 스크립트를 게임에 붙인다 (docs/ENGINE_SPEC.md).

* 페이즈가 시작되면 그 페이즈의 카드마다 라이브러리 진행단계의 `규칙`(`{"스크립트": "…"}`)을 읽어 `실행(카드)` 를 시작한다.
* 스크립트가 `기다리기(종류)` 를 만나면 멈추고, 플레이어의 입력(`answer`)이 오면 이어서 실행한다. 한 번의 실행은 `game.lock` 안에서
  끝까지(또는 다음 대기까지) 돌아서, 입력은 한 번에 하나씩 처리된다.
* 스크립트가 하는 일은 모두 엔진 함수(`CardHost`)를 거친다. 상태를 바꾸고 권한을 확인하는 것은 엔진이다.
* 화면 요청(`보이기`, `탭`, `알림`, `읽기`)은 게임에 쌓아 두었다가 `card_view` 가 보는 사람에게 허용된 것만 골라 돌려준다.
"""
import functools
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from . import clues, narrative
from .declare import BUILDER_NAMES, DECL_FUNCTIONS
from .script import VM, Program, Ref, ScriptError, Suspend, builtin_names, compile_expression, compile_source

MAX_ANSWER_BYTES = 2000
MAX_NOTICES = 20
ALL = "모두"
PUBLIC_FIELDS = ("이름", "직업", "나이", "성별")
CHARACTER_FIELDS = ("이름", "직업", "나이", "성별", "타임라인", "능력", "비밀", "목표", "범인", "NPC", "소개", "선택소개")


class AnswerError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class CardRun:
    key: str                         # "페이즈 칸 번호:진행단계 번호"
    library: dict[str, Any]
    row: dict[str, Any]              # 스냅샷의 진행구성 행(설정, 표시이름)
    program: Program | None = None
    vm: VM | None = None
    error: str | None = None
    done: bool = False
    screens: dict[Any, dict[str, dict[str, Any]]] = field(default_factory=dict)   # 대상(모두/계정) → 블록 이름 → 블록

    @property
    def title(self) -> str:
        return self.row.get("표시이름") or self.library.get("이름") or self.key

    @property
    def settings(self) -> dict[str, Any]:
        value = self.row.get("설정")
        return value if isinstance(value, dict) else {}


# ---- 호스트(스크립트가 부르는 엔진 기능) -------------------------------------------------------

MUTATING = {"배정취소", "탭이어쓰기", "변수설정", "배정", "투표", "투표초기화", "조사", "양도", "공개설정", "읽기", "기다리기", "단계_끝내기", "게임_종료"}
FUNCTION_NAMES = {
    "플레이어들", "플레이어수", "인물들", "공통스토리", "서사들", "배정된_플레이어수", "인물_없는_플레이어가_있다",
    "공통스토리부분들", "탭이어쓰기", "배정취소", "글", "선택지", "입력", "카드목록", "투표칸", "현황", "거부", "배정", "조사", "양도", "공개설정", "장소들", "모든_장소", "단서들", "보유목록", "받은공개", "인물찾기", "투표", "질문정의", "변수설정", "변수", "가지고_있다", "단서_보유자", "인물의_플레이어", "엔딩분기들", "후일담들", "조건_맞음", "모든_단서", "모든_인물", "서사_전체", "투표수", "최다득표", "투표초기화", "결과", "결과_인물", "결과_기타", "기타후보", "후보값", "읽기", "기다리기",
    "단계_끝내기", "게임_종료",
}
FUNCTION_NAMES |= BUILDER_NAMES          # 제작 화면을 정하는 함수들(app/declare.py). 게임 중에 불러도 값만 만들 뿐이다
CONSTANT_NAMES = {"통과", ALL}
MAX_INPUT_CHARS = 2000
MAX_CARDS = 200
CARD_ACTIONS = ("보여주기", "양도")
MAX_OPTION_CHARS = 50
MAX_VARIABLES = 500
MAX_VARIABLE_NAME = 100
MAX_VARIABLE_BYTES = 2000
MAX_CANDIDATES = 100


def known_names() -> set[str]:
    return FUNCTION_NAMES | CONSTANT_NAMES | builtin_names()


def condition_names() -> set[str]:
    """조건 식에서 부를 수 있는 이름. 상태를 바꾸는 함수는 뺀다(조건은 읽기만 한다)."""
    return known_names() - MUTATING


class CardHost:
    def __init__(self, game, run: CardRun, io, readonly: bool = False):
        self.game, self.run, self.io, self.readonly = game, run, io, readonly
        self.constants = {"통과": True, ALL: Ref(ALL)}
        self.functions: dict[str, Callable[..., Any]] = {}
        for name in FUNCTION_NAMES:
            self.functions[name] = DECL_FUNCTIONS[name] if name in DECL_FUNCTIONS else self._guard(name, getattr(self, "fn_" + name))

    def _guard(self, name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        if name not in MUTATING:
            return fn

        @functools.wraps(fn)
        def guarded(*args: Any, **kwargs: Any) -> Any:
            if self.readonly:
                raise ScriptError(f"진행 조건 안에서는 '{name}' 을(를) 쓸 수 없습니다")
            return fn(*args, **kwargs)

        return guarded

    # -- 읽기 --
    def fn_플레이어들(self) -> list[Ref]:
        return [Ref("플레이어", a) for a in self.game.players]

    def fn_플레이어수(self) -> int:
        return len(self.game.players)

    def fn_인물들(self) -> list[Ref]:
        return [Ref("인물", c["순서"]) for c in self.game.characters]

    def _common_story_parts(self) -> list[str]:
        """작품의 공통 스토리를 부분(본문)들로. 부분 표기가 없는 글은 부분 하나이다."""
        raw = ((self.game.snapshot.get("작품") or {}).get("공통스토리")) or ""
        return [p.text for p in narrative.split(raw)]

    def fn_공통스토리(self) -> str:
        """공통 스토리 전체(부분들을 이은 글)."""
        return "\n\n".join(self._common_story_parts())

    def fn_공통스토리부분들(self, 번호들: Any) -> str:
        """공통 스토리에서 번호(1부터)로 고른 부분들을 번호 순서로 이은 글. 없는 번호는 건너뛴다."""
        if not isinstance(번호들, (list, tuple)):
            raise ScriptError("공통스토리부분들() 에는 번호 목록을 넘겨야 합니다(예: [1, 2])")
        return narrative.pick(self._common_story_parts(), list(번호들))

    def fn_탭이어쓰기(self, 대상: Any, 이름: Any, 글내용: Any) -> None:
        """이미 있는 글 탭의 끝에 글을 이어 붙인다(탭의 자리는 그대로). 그 이름의 탭이 없으면 새 탭으로 만든다."""
        if not isinstance(대상, Ref) or 대상.kind not in (ALL, "플레이어"):
            raise ScriptError("탭이어쓰기() 의 대상은 모두 또는 플레이어여야 합니다")
        key = self._target_key(대상)
        name, text = str(이름), _text(글내용)
        old = self.game.tabs.get(key, {}).get(name)
        if old is None or old["내용"].get("종류") != "글":
            self.m_탭(대상, name, text)
            return
        merged = "\n\n".join(t for t in (str(old["내용"].get("내용", "")), text) if t)
        order = old["순번"]                                         # 탭이 놓인 자리는 바꾸지 않는다
        self.m_탭(대상, name, merged)
        self.game.tabs[key][name]["순번"] = order

    def fn_서사들(self, 인물: Any, 번호들: Any) -> str:
        if 인물 is None:
            return ""
        slot = self._character_slot(인물)
        row = self._character(slot)
        if not isinstance(번호들, (list, tuple)):
            raise ScriptError("서사들() 의 두 번째 값은 번호 목록이어야 합니다(예: [1, 2])")
        parts = row.get("서사_부분")
        if isinstance(parts, list):                       # 확정할 때 해석해 둔 부분 목록
            return narrative.pick([str(p.get("본문", "")) for p in parts], list(번호들))
        return narrative.numbered(row.get("서사") or "", list(번호들))

    def fn_장소들(self) -> list[Ref]:
        """조사할 수 있는 장소들(가장 안쪽 장소)."""
        return [Ref("장소", p["순서"]) for p in clues.leaf_places(self.game)]

    def fn_모든_장소(self) -> list[Ref]:
        """작품의 모든 장소(바깥 장소 포함). 능력의 지목 대상처럼 조사 단위가 아니어도 고를 수 있는 장소에 쓴다."""
        return [Ref("장소", p["순서"]) for p in sorted(self.game.snapshot.get("장소") or [], key=lambda p: p["순서"])]

    def fn_단서들(self) -> list[Ref]:
        """작품의 모든 단서(누가 가졌는지와 상관없이, 증언은 제외). 화면에는 공개이름이 보인다."""
        return [Ref("단서", c["순서"]) for c in sorted(self.game.snapshot.get("단서") or [], key=lambda c: c["순서"])]

    def fn_보유목록(self, 플레이어: Any) -> list[dict[str, Any]]:
        """이 플레이어가 지금 가진 단서·증언(얻은 순서). 각 항목은 {종류, 이름, 공개이름, 내용, 장소}."""
        return clues.holdings_of(self.game, self._player_account(플레이어))

    def fn_인물찾기(self, 순서: Any) -> Ref | None:
        """인물의 순서 번호로 인물을 찾는다(NPC 포함). 없으면 None. 카드 설정에 적힌 번호를 인물로 바꿀 때 쓴다."""
        if not _is_int(순서) or not any(c["순서"] == 순서 for c in self.game.snapshot.get("인물") or []):
            return None
        return Ref("인물", 순서)

    # -- 게임 변수와 상태 읽기(엔딩·후일담의 조건이 쓴다) --
    def fn_변수설정(self, 이름: str, 값: Any) -> None:
        """게임 변수를 정한다. 값은 글자, 숫자, 참/거짓, 없음, 목록, 사전만 되고 작아야 한다. 이름 하나당 값 하나이다."""
        name = str(이름)
        if not name or len(name) > MAX_VARIABLE_NAME:
            raise ScriptError(f"변수 이름은 1자 이상 {MAX_VARIABLE_NAME}자 이하여야 합니다")
        try:
            text = json.dumps(값, ensure_ascii=False)
        except (TypeError, ValueError):
            raise ScriptError("변수에는 글자, 숫자, 참/거짓, 목록, 사전만 담을 수 있습니다") from None
        if len(text) > MAX_VARIABLE_BYTES:
            raise ScriptError(f"변수 값이 너무 큽니다(최대 {MAX_VARIABLE_BYTES}자)")
        if name not in self.game.variables and len(self.game.variables) >= MAX_VARIABLES:
            raise ScriptError(f"변수는 {MAX_VARIABLES}개까지 만들 수 있습니다")
        self.game.variables[name] = json.loads(text)

    def fn_변수(self, 이름: str, 기본값: Any = None) -> Any:
        """게임 변수의 값. 정한 적이 없으면 기본값(없으면 None)."""
        value = self.game.variables.get(str(이름), 기본값)
        return json.loads(json.dumps(value))            # 스크립트가 받은 값을 바꿔도 원본은 그대로

    def fn_가지고_있다(self, 플레이어: Any, 단서이름: str) -> bool:
        """이 플레이어가 그 이름의 단서를 지금 가지고 있는지."""
        return any(c["종류"] == "단서" and c["이름"] == 단서이름 for c in clues.holdings_of(self.game, self._player_account(플레이어)))

    def fn_단서_보유자(self, 단서이름: str) -> Ref | None:
        """그 이름의 단서를 지금 가진 플레이어. 아무도 갖지 않았으면 None."""
        for account in self.game.players:
            if any(c["종류"] == "단서" and c["이름"] == 단서이름 for c in clues.holdings_of(self.game, account)):
                return Ref("플레이어", account)
        return None

    def fn_인물의_플레이어(self, 인물: Any) -> Ref | None:
        """그 인물을 맡은 플레이어. 아무도 맡지 않았으면 None."""
        if not (isinstance(인물, Ref) and 인물.kind == "인물"):
            return None
        for player in self.game.players.values():
            if player.character == 인물.key:
                return Ref("플레이어", player.account_id)
        return None

    def fn_모든_단서(self) -> list[dict[str, Any]]:
        """작품의 모든 단서와 증언(누가 가졌는지와 상관없이). 전체 공개 단계가 보여 준다. 각 항목은 {종류, 이름, 공개이름, 내용, 장소}."""
        out = []
        for kind in ("단서", "증언"):
            for row in sorted(self.game.snapshot.get(kind) or [], key=lambda r: r["순서"]):
                out.append(clues.describe(self.game, kind, row))
        return out

    def fn_모든_인물(self) -> list[Ref]:
        """NPC 를 포함한 작품의 모든 인물."""
        return [Ref("인물", c["순서"]) for c in sorted(self.game.snapshot.get("인물") or [], key=lambda c: c["순서"])]

    def fn_서사_전체(self, 인물: Any) -> str:
        """인물의 서사를 모든 부분을 이어서 돌려준다(전체 공개 단계용)."""
        if not (isinstance(인물, Ref) and 인물.kind == "인물"):
            raise ScriptError("서사_전체() 에는 인물을 넘겨야 합니다")
        row = self._character(인물.key)
        parts = row.get("서사_부분")
        texts = [str(p.get("본문", "")) for p in parts] if isinstance(parts, list) else [p.text for p in narrative.split(row.get("서사") or "")]
        return "\n\n".join(texts)

    def fn_엔딩분기들(self) -> list[Ref]:
        return [Ref("엔딩분기", r["순서"]) for r in sorted(self.game.snapshot.get("엔딩분기") or [], key=lambda r: r["순서"])]

    def fn_후일담들(self) -> list[Ref]:
        return [Ref("후일담", r["순서"]) for r in sorted(self.game.snapshot.get("후일담") or [], key=lambda r: r["순서"])]

    def fn_조건_맞음(self, 항목: Any) -> bool:
        """엔딩 분기나 후일담의 조건이 지금 맞는지. 조건이 비어 있으면 항상 맞는다. 조건이 잘못되었으면 맞지 않는 것으로 보고
        카드 오류로 알린다(게임은 멈추지 않는다)."""
        if not (isinstance(항목, Ref) and 항목.kind in ("엔딩분기", "후일담")):
            raise ScriptError("조건_맞음() 에는 엔딩분기들()·후일담들() 의 항목을 넘겨야 합니다")
        row = self._row(항목)
        condition = row.get("조건")
        if not condition:
            return True
        expression = condition.get("식") if isinstance(condition, dict) else None
        if not isinstance(expression, str) or not expression.strip():
            self.run.error = f"{항목.kind} '{row.get('이름') or row['순서']}' 의 조건은 {{\"식\": \"…\"}} 모양이어야 합니다"
            return False
        key = ("식", expression)
        if key not in self.game.programs:
            try:
                self.game.programs[key] = (compile_expression(expression, condition_names()), None)
            except ScriptError as err:
                self.game.programs[key] = (None, f"조건 식 오류: {err}")
        program, error = self.game.programs[key]
        if program is None:
            self.run.error = f"{항목.kind} '{row.get('이름') or row['순서']}': {error}"
            return False
        vm = VM(program, CardHost(self.game, self.run, None, readonly=True))
        try:
            vm.start("조건", [])
            vm.run()
        except ScriptError as err:
            self.run.error = f"{항목.kind} '{row.get('이름') or row['순서']}' 의 조건을 계산하지 못했습니다: {err}"
            return False
        return bool(vm.result)

    def _row(self, ref: Ref) -> dict[str, Any]:
        row = next((r for r in self.game.snapshot.get(ref.kind) or [] if r["순서"] == ref.key), None)
        if row is None:
            raise ScriptError(f"없는 {ref.kind} 입니다")
        return row

    def fn_질문정의(self, 정의: Any) -> dict[str, Any] | None:
        """카드 설정에 적은 질문을 {질문, 선택, 글자수} 로 정리한다. 글자만 적으면 자유롭게 쓰는 질문이고, {"질문": …, "선택": [...]} 이면
        고르는 질문이다. 읽을 수 없으면 None."""
        if isinstance(정의, str) and 정의.strip():
            return {"질문": 정의.strip(), "선택": [], "글자수": 300}
        if not isinstance(정의, dict) or not isinstance(정의.get("질문"), str) or not 정의["질문"].strip():
            return None
        choices = [c.strip() for c in (정의.get("선택") or []) if isinstance(c, str) and c.strip() and len(c.strip()) <= MAX_OPTION_CHARS]
        limit = 정의.get("글자수")
        if not _is_int(limit) or not 1 <= limit <= MAX_INPUT_CHARS:
            limit = 300
        return {"질문": 정의["질문"].strip(), "선택": list(dict.fromkeys(choices))[:MAX_CANDIDATES], "글자수": limit}

    def fn_기타후보(self, 값: Any) -> str | None:
        """인물이 아닌 투표 선택지(예: "사고사")로 쓸 수 있는 글이면 그 글, 아니면 None. 카드 설정의 후보를 읽을 때 쓴다."""
        if isinstance(값, str) and 값.strip() and len(값.strip()) <= MAX_OPTION_CHARS:
            return 값.strip()
        return None

    def fn_후보값(self, 후보: Any) -> Any:
        """후보의 값. 인물이면 순서 번호, 인물이 아닌 선택지이면 그 글. 투표칸이 돌려주는 값과 견줄 때 쓴다."""
        return 후보.key if isinstance(후보, Ref) and 후보.kind == "인물" else 후보

    def fn_투표수(self, 이름: str) -> int:
        """이 투표에 투표한 사람 수."""
        return len(self.game.votes.get(str(이름), {}))

    def fn_최다득표(self, 이름: str) -> list[Any]:
        """가장 많은 표를 받은 후보들(인물은 인물, 그 밖의 선택지는 글). 동률이면 여럿, 투표가 없으면 빈 목록."""
        counts = _tally(self.game, str(이름))
        top = max(counts.values(), default=0)
        keys = sorted((k for k, n in counts.items() if n == top and top > 0), key=lambda k: (isinstance(k, str), str(k) if isinstance(k, str) else k))
        return [Ref("인물", k) if isinstance(k, int) else k for k in keys]

    def fn_결과(self, 이름: str) -> Any:
        """이 투표에서 가장 많은 표를 받은 후보. 인물이면 인물, 그 밖의 선택지(예: "사고사")이면 그 글이다.
        동률이거나 투표가 없으면 None(구속 없음). 지금 있는 표로 그때그때 계산한다."""
        top = self.fn_최다득표(이름)
        return top[0] if len(top) == 1 else None

    def fn_결과_인물(self, 이름: str) -> Ref | None:
        """`결과` 가 인물일 때 그 인물, 아니면 None."""
        result = self.fn_결과(이름)
        return result if isinstance(result, Ref) else None

    def fn_결과_기타(self, 이름: str) -> str | None:
        """`결과` 가 인물이 아닌 선택지일 때 그 글, 아니면 None."""
        result = self.fn_결과(이름)
        return result if isinstance(result, str) else None

    def fn_받은공개(self, 플레이어: Any) -> list[dict[str, Any]]:
        """다른 사람이 이 플레이어에게(또는 전체에게) 보여 준 단서. 각 항목은 {종류, 이름, 내용, 장소, 주인}."""
        return clues.revealed_to(self.game, self._player_account(플레이어))

    def fn_배정된_플레이어수(self) -> int:
        return sum(1 for p in self.game.players.values() if p.character is not None)

    def fn_인물_없는_플레이어가_있다(self) -> bool:
        return any(p.character is None for p in self.game.players.values())

    # -- 블록 만들기 --
    def fn_글(self, 이름: str, 내용: Any) -> dict[str, Any]:
        return {"종류": "글", "이름": str(이름), "내용": _text(내용)}

    def fn_선택지(self, 이름: str, 항목: Any, 한사람당: int = 1, 확인필요: bool = False, 소개보임: bool = False) -> dict[str, Any]:
        """고르는 칸. 인물을 고르는 칸이면 `소개보임` 으로 인물의 선택 화면 소개(`선택소개`)를 함께 보여 줄 수 있다."""
        if not isinstance(항목, (list, tuple)):
            raise ScriptError("선택지의 항목은 목록이어야 합니다")
        return {
            "종류": "선택지", "이름": str(이름), "항목": list(항목), "한사람당": 한사람당, "확인필요": bool(확인필요), "소개보임": bool(소개보임),
            "질문ID": f"{self.run.key}:확인",
        }

    def fn_입력(self, 이름: str, 질문: Any, 글자수: int = 300) -> dict[str, Any]:
        """글자를 받는 칸. 플레이어가 보내면 `기다리기(이름)` 이 `{플레이어, 값}` 을 돌려준다."""
        name = str(이름)
        if ":" in name or name in ("확인", ""):
            raise ScriptError("입력의 이름은 비워 둘 수 없고 ':' 이나 '확인' 일 수 없습니다")
        if not isinstance(글자수, int) or isinstance(글자수, bool) or not 1 <= 글자수 <= MAX_INPUT_CHARS:
            raise ScriptError(f"입력의 글자수는 1 이상 {MAX_INPUT_CHARS} 이하여야 합니다")
        return {"종류": "입력", "이름": name, "질문": _text(질문), "글자수": 글자수, "질문ID": f"{self.run.key}:{name}"}

    def fn_카드목록(self, 이름: str, 항목: Any, 동작: Any = None) -> dict[str, Any]:
        """단서·증언 같은 카드를 앞면이 보이도록 늘어놓는 블록. 항목은 `보유목록()`·`받은공개()` 가 돌려준 목록이다.

        `동작` 에 ["보여주기", "양도"] 중 쓸 것을 넘기면 카드마다 그 버튼이 생기고, 누르면 `기다리기(이름)` 이
        `{플레이어, 값: {동작, 단서, 대상}}` 을 돌려준다(대상은 "전체" 이거나 계정 번호 목록).
        """
        name = str(이름)
        if not isinstance(항목, (list, tuple)):
            raise ScriptError("카드목록의 항목은 목록이어야 합니다")
        actions = [] if 동작 is None else list(동작)
        if any(a not in CARD_ACTIONS for a in actions):
            raise ScriptError(f"카드목록의 동작은 {', '.join(CARD_ACTIONS)} 중에서 골라야 합니다")
        if actions and (":" in name or name in ("확인", "")):
            raise ScriptError("동작이 있는 카드목록의 이름은 비워 둘 수 없고 ':' 이나 '확인' 일 수 없습니다")
        cards = []
        for item in list(항목)[:MAX_CARDS]:
            if not isinstance(item, dict):
                raise ScriptError("카드목록의 항목은 보유목록() 이 돌려준 카드여야 합니다")
            card = {k: _text(item.get(k)) for k in ("종류", "이름", "공개이름", "내용", "장소", "주인")}
            if isinstance(item.get("순서"), int):
                card["순서"] = item["순서"]
            if isinstance(item.get("양도가능"), bool):
                card["양도가능"] = item["양도가능"]
            shared = item.get("공개")
            if shared == "전체" or isinstance(shared, list):
                card["공개"] = shared if shared == "전체" else [t for t in shared if isinstance(t, int)]
            cards.append(card)
        block = {"종류": "카드목록", "이름": name, "항목": cards}
        if actions:
            block.update({"동작": actions, "질문ID": f"{self.run.key}:{name}"})
        return block

    def fn_투표칸(self, 이름: str, 후보: Any, 질문: Any = "") -> dict[str, Any]:
        """비공개 투표 칸. 후보는 인물이나 인물이 아닌 선택지(글, 예: "사고사")의 목록이다. 플레이어는 다음 단계로 가기 전까지
        다시 골라 바꿀 수 있고, 자기 인물은 고를 수 없다. 투표하면 `기다리기(이름)` 이 `{플레이어, 값}` 을 돌려준다
        (값은 인물이면 순서 번호, 선택지이면 그 글)."""
        name = str(이름)
        if ":" in name or name in ("확인", ""):
            raise ScriptError("투표칸의 이름은 비워 둘 수 없고 ':' 이나 '확인' 일 수 없습니다")
        if not isinstance(후보, (list, tuple)) or not 후보 or len(후보) > MAX_CANDIDATES:
            raise ScriptError(f"투표칸의 후보는 1개 이상 {MAX_CANDIDATES}개 이하의 목록이어야 합니다")
        options: list[Any] = []
        for c in 후보:
            if isinstance(c, Ref) and c.kind in VOTE_REF_KINDS:
                options.append(c)
            elif isinstance(c, str) and c.strip() and len(c.strip()) <= MAX_OPTION_CHARS:
                options.append(c.strip())
            else:
                raise ScriptError("투표칸의 후보는 인물·장소·단서나 글이어야 합니다")
        if len({_vote_value(c) for c in options}) != len(options):
            raise ScriptError("투표칸의 후보가 겹칩니다")
        self.game.vote_options[name] = {v for v in (_vote_value(c) for c in options) if isinstance(v, str)}
        return {"종류": "투표", "이름": name, "질문": _text(질문), "항목": options, "질문ID": f"{self.run.key}:{name}"}

    def fn_현황(self, 이름: str, 완료: int, 전체: int) -> dict[str, Any]:
        return {"종류": "현황", "이름": str(이름), "완료": int(완료), "전체": int(전체)}

    def fn_거부(self, 메시지: Any) -> dict[str, Any]:
        return {"거부": _text(메시지)}

    # -- 엔진 명령 --
    def fn_조사(self, 플레이어: Any, 장소: Any) -> dict[str, Any] | None:
        """장소에서 항목 하나를 얻는다. 얻은 {종류, 이름, 내용, 장소} 를 돌려주고, 얻을 것이 없거나 장소가 아니면 None."""
        account = self._player_account(플레이어)
        slot = 장소.key if isinstance(장소, Ref) and 장소.kind == "장소" else 장소
        if not isinstance(slot, int) or isinstance(slot, bool):         # 플레이어가 보낸 값이라 잘못되어도 카드가 멈추지 않는다
            return None
        return clues.investigate(self.game, account, slot, self.io)

    def fn_양도(self, 플레이어: Any, 받는사람: Any, 단서: Any) -> bool:
        """단서를 다른 플레이어에게 바로 넘긴다(수락이 필요 없다). 성공하면 True. 그 단서에 걸린 공개는 사라진다."""
        giver = self._player_account(플레이어)
        taker = 받는사람.key if isinstance(받는사람, Ref) and 받는사람.kind == "플레이어" else 받는사람
        if not (_is_int(taker) and _is_int(단서)):
            return False
        return clues.transfer(self.game, giver, taker, 단서, self.io)

    def fn_공개설정(self, 플레이어: Any, 단서: Any, 대상: Any) -> bool:
        """단서를 볼 수 있는 사람을 바꾸어 놓는다. 대상은 "전체", 플레이어(계정 번호) 목록이며 빈 목록이면 공개를 모두 취소한다."""
        owner = self._player_account(플레이어)
        if not _is_int(단서):
            return False
        if isinstance(대상, (list, tuple)):
            대상 = [t.key if isinstance(t, Ref) and t.kind == "플레이어" else t for t in 대상]
        return clues.set_reveal(self.game, owner, 단서, 대상, self.io)

    def fn_투표(self, 이름: str, 플레이어: Any, 후보: Any) -> bool:
        """플레이어의 표를 기록한다(이미 했으면 바꾼다). 후보는 인물, 인물의 순서 번호, 또는 투표칸에 둔 선택지 글이다.
        없는 후보이거나 자기 인물이면 False."""
        account = self._player_account(플레이어)
        name = str(이름)
        value = _vote_value(후보) if isinstance(후보, Ref) and 후보.kind in VOTE_REF_KINDS else 후보
        if _is_int(value):
            if not any(c["순서"] == value for c in self.game.snapshot.get("인물") or []):
                return False
            if self.game.players[account].character == value:
                return False
        elif not (isinstance(value, str) and value in self.game.vote_options.get(name, set())):
            return False
        self.game.votes.setdefault(name, {})[account] = value
        return True

    def fn_투표초기화(self, 이름: str) -> None:
        """이 투표의 표를 모두 지운다(재투표를 시작할 때)."""
        self.game.votes.pop(str(이름), None)

    def fn_배정(self, 플레이어: Any, 인물: Any) -> bool:
        from .engine import AssignError, assign_character

        account = self._player_account(플레이어)
        try:
            slot = self._character_slot(인물)
            self._character(slot)
        except ScriptError:                                              # 플레이어가 보낸 값이라 잘못되어도 카드가 멈추지 않는다
            return False
        try:
            assign_character(self.game, account, slot, lambda a, s: self.io.assign(a, s))
        except AssignError:
            return False
        return True

    def fn_배정취소(self, 플레이어: Any) -> bool:
        """플레이어가 확인했던 인물을 되돌린다. 고른 인물이 없으면 False."""
        from .engine import AssignError, unassign_character

        account = self._player_account(플레이어)
        try:
            unassign_character(self.game, account, lambda a, s: self.io.assign(a, s))
        except AssignError:
            return False
        return True

    def fn_읽기(self, 대상: Any, 이름: str, 내용: Any) -> None:
        target, name = 대상, 이름
        accounts = self._target_accounts(target)
        qid = f"{self.run.key}:읽기:{name}"
        record = self.game.reads.setdefault(qid, {"필요": set(), "확인": set()})
        record["필요"].update(accounts)
        block = {"종류": "읽기", "이름": str(name), "내용": _text(내용), "질문ID": qid}
        for key in ([ALL] if target.kind == ALL else [target.key]):
            self.run.screens.setdefault(key, {})[str(name)] = block

    def fn_기다리기(self, 종류: str, *더: str) -> Any:
        """플레이어의 입력을 기다린다. 종류를 여럿 주면 그중 아무 것이나 오면 이어서 실행하고, 돌려주는 값의 `종류` 로 무엇이 왔는지 안다."""
        kinds = [str(종류), *[str(k) for k in 더]]
        raise Suspend({"종류": kinds[0], "종류들": kinds})

    def fn_단계_끝내기(self) -> bool:
        self.game.end_requested = True
        return True

    def fn_게임_종료(self) -> None:
        from .engine import end_game

        end_game(self.game, self.io.end)

    # -- 대상의 값 --
    def getattr(self, ref: Ref, name: str) -> Any:
        if ref.kind == "플레이어":
            player = self.game.players.get(ref.key)
            if player is None:
                raise ScriptError("게임에 없는 플레이어입니다")
            if name == "인물":
                return None if player.character is None else Ref("인물", player.character)
            if name == "이름":
                return player.nickname
            if name == "계정":
                return player.account_id
        elif ref.kind == "인물":
            row = self._character(ref.key)
            if name == "순서":
                return row["순서"]
            if name == "서사":
                raise ScriptError("서사는 서사들(인물, 번호들) 로 읽으세요")
            if name == "NPC":
                return bool(row.get("NPC")) or row["순서"] in self.game.npc_slots     # 이 게임의 인원 때문에 NPC 가 된 인물도 포함
            if name in CHARACTER_FIELDS:
                return row.get(name)
        elif ref.kind == "엔딩분기":
            row = self._row(ref)
            if name in ("이름", "내용"):
                return row.get(name)
            if name == "순서":
                return row["순서"]
        elif ref.kind == "후일담":
            row = self._row(ref)
            if name == "내용":
                return row.get("내용")
            if name == "순서":
                return row["순서"]
            if name == "인물":
                return None if row.get("인물_순서") is None else Ref("인물", row["인물_순서"])
        elif ref.kind == "카드":
            if name == "설정":
                return json.loads(json.dumps(self.run.settings))     # 스크립트가 바꿔도 원본은 그대로
            if name == "이름":
                return self.run.library.get("이름")
            if name == "표시이름":
                return self.run.title
            if name == "차수":
                return _ordinal_prefix(self.run.title, self.run.library.get("이름"))
        raise ScriptError(f"{ref.kind} 의 '{name}' 을(를) 읽을 수 없습니다")

    def method(self, ref: Ref, name: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
        if ref.kind in (ALL, "플레이어") and name in ("보이기", "탭", "알림"):
            if self.readonly:
                raise ScriptError(f"진행 조건 안에서는 '{name}' 을(를) 쓸 수 없습니다")
            if kwargs:
                raise ScriptError(f"'{name}' 은(는) 이름 붙인 인자를 받지 않습니다")
            return getattr(self, "m_" + name)(ref, *args)
        raise ScriptError(f"{ref.kind} 에는 '{name}' 메서드가 없습니다")

    def m_보이기(self, ref: Ref, block: Any) -> None:
        if not isinstance(block, dict) or "종류" not in block:
            raise ScriptError("보이기() 에는 글(), 선택지(), 입력(), 현황() 같은 블록을 넘겨야 합니다")
        key = self._target_key(ref)
        self.run.screens.setdefault(key, {})[str(block.get("이름", "블록"))] = dict(block)

    def m_탭(self, ref: Ref, name: str, content: Any) -> None:
        key = self._target_key(ref)
        block = content if isinstance(content, dict) and "종류" in content else {"종류": "글", "이름": str(name), "내용": _text(content)}
        self.game.tab_counter += 1
        self.game.tabs.setdefault(key, {})[str(name)] = {
            "내용": dict(block), "카드": self.run.key, "위치": self.game.phase_index,
            "유지": bool(self.run.settings.get("내용유지", True)), "순번": self.game.tab_counter,
        }

    def m_알림(self, ref: Ref, text: Any) -> None:
        for account in self._target_accounts(ref):
            self.game.notice_counter += 1
            notices = self.game.notices.setdefault(account, [])
            notices.append({"번호": self.game.notice_counter, "글": _text(text)})
            del notices[:-MAX_NOTICES]

    # -- 내부 --
    def _player_account(self, player: Any) -> int:
        if not (isinstance(player, Ref) and player.kind == "플레이어" and player.key in self.game.players):
            raise ScriptError("플레이어가 아닙니다")
        return player.key

    def _character_slot(self, character: Any) -> int:
        if isinstance(character, Ref) and character.kind == "인물":
            return character.key
        if isinstance(character, int) and not isinstance(character, bool):      # 선택지에서 고른 값(인물의 순서)
            return character
        raise ScriptError("인물이 아닙니다")

    def _character(self, slot: int) -> dict[str, Any]:
        for c in self.game.snapshot.get("인물") or []:
            if c["순서"] == slot:
                return c
        raise ScriptError("없는 인물입니다")

    def _target_key(self, ref: Ref) -> Any:
        if ref.kind == ALL:
            return ALL
        if ref.key not in self.game.players:
            raise ScriptError("게임에 없는 플레이어입니다")
        return ref.key

    def _target_accounts(self, ref: Any) -> list[int]:
        if not isinstance(ref, Ref) or ref.kind not in (ALL, "플레이어"):
            raise ScriptError("대상은 모두 또는 플레이어여야 합니다")
        if ref.kind == ALL:
            return list(self.game.players)
        if ref.key not in self.game.players:
            raise ScriptError("게임에 없는 플레이어입니다")
        return [ref.key]


def _ordinal_prefix(title: str, library_name: Any) -> str:
    """같은 진행단계를 여러 번 놓았을 때 둘째부터 붙는 "2차 " 같은 앞말. 하나뿐이거나 첫째이면 빈 글.

    카드의 표시 이름은 같은 이름이 여럿일 때 "1차 이름", "2차 이름" 이 된다(첫째는 "1차 "이지만 탭 이름에는 붙이지 않는다)."""
    match = re.fullmatch(r"(\d+)차 (.*)", title or "", re.S)
    if match and match.group(2) == library_name and int(match.group(1)) >= 2:
        return f"{match.group(1)}차 "
    return ""


def _tally(game, name: str) -> dict[int | str, int]:
    counts: dict[int | str, int] = {}
    for slot in game.votes.get(name, {}).values():
        counts[slot] = counts.get(slot, 0) + 1
    return counts


VOTE_REF_KINDS = ("인물", "장소", "단서")


def _vote_value(option: Any) -> Any:
    """투표칸 후보의 값. 인물은 순서 번호, 장소·단서는 "장소:2" 같은 글, 글은 그대로."""
    if isinstance(option, Ref):
        return option.key if option.kind == "인물" else f"{option.kind}:{option.key}"
    return option


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _text(value: Any) -> str:
    if isinstance(value, dict) and "내용" in value:
        return str(value["내용"])
    if isinstance(value, Ref):
        raise ScriptError("대상을 글자로 쓸 수 없습니다")
    return "" if value is None else str(value)


# ---- 페이즈 시작과 카드 실행 --------------------------------------------------------------------

def _program_for(game, library: dict[str, Any]) -> tuple[Program | None, str | None]:
    """라이브러리 항목의 스크립트를 번역한다(게임 안에서 한 번만). 스크립트가 없으면 (None, None)."""
    key = library.get("번호")
    if key in game.programs:
        return game.programs[key]
    rule = library.get("규칙")
    source = rule.get("스크립트") if isinstance(rule, dict) else None
    if not isinstance(source, str) or not source.strip():
        result: tuple[Program | None, str | None] = (None, None)
    else:
        try:
            result = (compile_source(source, known_names()), None)
        except ScriptError as err:
            result = (None, f"스크립트 오류: {err}")
    game.programs[key] = result
    return result


def start_phase(game, io) -> None:
    """지금 페이즈의 카드를 만들어 실행을 시작한다(게임 시작과 페이즈 전환 때). 이전 페이즈의 카드와 대기는 모두 끝난다."""
    game.runs = {}
    game.card_conditions = []
    game.end_requested = False
    slot = game.phase["순서"]
    library = {item["번호"]: item for item in ((game.snapshot.get("라이브러리") or {}).get("진행단계") or [])}
    for row in game.snapshot.get("진행구성") or []:
        if row.get("진행순서_순서") != slot or row.get("진행단계_번호") not in library:
            continue
        lib = library[row["진행단계_번호"]]
        run = CardRun(key=f"{slot}:{lib['번호']}", library=lib, row=row)
        run.program, run.error = _program_for(game, lib)
        game.runs[run.key] = run
    for run in game.runs.values():
        if run.program and "진행조건" in run.program.funcs:
            game.card_conditions.append(_condition(run))
    for run in list(game.runs.values()):
        if run.program and "실행" in run.program.funcs:
            run.vm = VM(run.program, CardHost(game, run, io))
            run.vm.start("실행", [Ref("카드", run.key)])
            _run(game, run)
    pump_end_requests(game, io)


def _run(game, run: CardRun) -> None:
    """멈출 곳(끝 또는 입력 대기)까지 실행한다. 오류는 그 카드에만 남기고 게임은 계속된다."""
    try:
        status = run.vm.run()
        run.done = status == "done"
    except ScriptError as err:
        run.error, run.done, run.vm = f"스크립트 오류: {err}", True, None
    except Exception as err:      # 엔진 쪽 문제가 한 카드 때문에 게임 전체를 멈추게 하지 않는다
        run.error, run.done, run.vm = f"내부 오류: {type(err).__name__}", True, None


def pump_end_requests(game, io) -> None:
    """스크립트가 `단계_끝내기()` 를 불렀으면 다음 단계로 넘어간다(진행 조건은 지킨다)."""
    from .engine import AdvanceError, _advance

    while game.end_requested:
        game.end_requested = False
        try:
            _advance(game, io)
        except AdvanceError:
            return


def _condition(run: CardRun) -> Callable[[Any], str | None]:
    def check(game) -> str | None:
        host = CardHost(game, run, None, readonly=True)
        vm = VM(run.program, host)
        try:
            vm.start("진행조건", [Ref("카드", run.key)])
            if vm.run() != "done":
                raise ScriptError("진행 조건에서는 기다릴 수 없습니다")
        except ScriptError as err:
            run.error = f"진행 조건 오류: {err}"           # 고장 난 조건이 게임을 영원히 막지는 않는다
            return None
        result = vm.result
        return str(result["거부"]) if isinstance(result, dict) and "거부" in result else None

    return check


# ---- 입력 ------------------------------------------------------------------------------------

def _card_action_block(game, run, name: str) -> dict[str, Any] | None:
    """이 카드가 보여 주는 동작이 있는 카드목록 블록(탭이든 화면이든)."""
    candidates = [b for per in run.screens.values() for b in per.values()]
    candidates += [t["내용"] for per in game.tabs.values() for t in per.values() if t["카드"] == run.key]
    return next((b for b in candidates if b.get("종류") == "카드목록" and b.get("동작") and b.get("이름") == name), None)


def _clean_card_action(game, account_id: int, block: dict[str, Any], value: Any) -> dict[str, Any]:
    """카드의 버튼에서 온 값을 검사해 `{동작, 단서, 대상}` 로 돌려준다. 모양이 맞지 않으면 거부한다(스크립트가 잘못된 값에 멈추지 않게)."""
    bad = AnswerError("invalid", "보낸 값을 읽을 수 없습니다")
    if not isinstance(value, dict) or value.get("동작") not in block["동작"] or not _is_int(value.get("단서")):
        raise bad
    targets = value.get("대상")
    if targets != "전체":
        if not isinstance(targets, list) or len(targets) > len(game.players):
            raise bad
        if any(not _is_int(t) or t not in game.players or t == account_id for t in targets):
            raise bad
    if value["동작"] == "양도" and (targets == "전체" or len(targets) != 1):
        raise bad
    return {"동작": value["동작"], "단서": value["단서"], "대상": targets}


def answer(game, account_id: int, qid: str, value: Any, io) -> None:
    """플레이어의 입력을 받는다. 질문 ID 가 지금 받는 것이 아니면 거부한다. 호출하는 쪽이 `game.lock` 을 잡는다."""
    if game.ended:
        raise AnswerError("ended", "게임이 끝났습니다")
    if account_id not in game.players:
        raise AnswerError("not_player", "플레이어만 답할 수 있습니다")
    try:
        if len(json.dumps(value, ensure_ascii=False)) > MAX_ANSWER_BYTES:
            raise AnswerError("invalid", "값이 너무 깁니다")
    except TypeError:
        raise AnswerError("invalid", "값을 읽을 수 없습니다") from None
    run = next((r for r in game.runs.values() if qid.startswith(r.key + ":")), None)
    if run is None:
        raise AnswerError("stale", "지금은 받지 않는 질문입니다")
    rest = qid[len(run.key) + 1:]
    if rest.startswith("읽기:"):
        record = game.reads.get(qid)
        if record is None or account_id not in record["필요"]:
            raise AnswerError("stale", "지금은 받지 않는 질문입니다")
        if account_id not in record["확인"]:
            record["확인"].add(account_id)
            game.bump()
        return
    vm = run.vm
    if vm is None or vm.waiting is None or rest not in (vm.waiting.get("종류들") or [vm.waiting.get("종류")]):
        raise AnswerError("stale", "지금은 받지 않는 질문입니다")
    action_block = _card_action_block(game, run, rest)
    if action_block is not None:
        value = _clean_card_action(game, account_id, action_block, value)
    vote_block = next((b for t in run.screens.values() for b in t.values() if b.get("종류") == "투표" and b.get("이름") == rest), None)
    if vote_block is not None and not (_is_int(value) or (isinstance(value, str) and 0 < len(value) <= MAX_OPTION_CHARS)):
        raise AnswerError("invalid", "고른 후보를 읽을 수 없습니다")
    block = next((b for t in run.screens.values() for b in t.values() if b.get("종류") == "입력" and b.get("이름") == rest), None)
    if block is not None:
        if not isinstance(value, str) or not value.strip():
            raise AnswerError("invalid", "글자를 입력해 주세요")
        if len(value) > block["글자수"]:
            raise AnswerError("invalid", f"{block['글자수']}자까지 쓸 수 있습니다")
        value = value.strip()
    vm.host.io = io                                  # 기록은 이 요청의 연결로 쓴다(시작 때의 연결은 이미 닫혔다)
    vm.resume({"플레이어": Ref("플레이어", account_id), "값": value, "종류": rest})
    _run(game, run)
    pump_end_requests(game, io)
    game.bump()


# ---- 보는 사람에게 보여 줄 것 ----------------------------------------------------------------------

def _item(game, viewer: int, item: Any, show_intro: bool = False) -> dict[str, Any]:
    if isinstance(item, Ref) and item.kind == "인물":
        row = next((c for c in game.snapshot.get("인물") or [] if c["순서"] == item.key), None)
        taken = next((p.account_id for p in game.players.values() if p.character == item.key), None)
        shown = {"선택소개": (row or {}).get("선택소개")} if show_intro else {}
        return {"값": item.key, **{f: (row or {}).get(f) for f in PUBLIC_FIELDS}, **shown, "선택한_계정": taken}
    if isinstance(item, Ref) and item.kind == "장소":
        place = next((p for p in game.snapshot.get("장소") or [] if p["순서"] == item.key), None) or {}
        active = viewer in game.players and clues.next_item(game, viewer, item.key) is not None
        return {
            "값": item.key, "이름": clues.place_path(game, item.key), "유형": place.get("유형"), "특징": place.get("특징"),
            "비활성": not active,
        }
    if isinstance(item, Ref):
        return {"값": None, "이름": item.kind}
    return {"값": item, "이름": str(item)}


def _clue_label(game, order: int) -> str:
    row = next((c for c in game.snapshot.get("단서") or [] if c["순서"] == order), None) or {}
    return row.get("공개이름") or row.get("이름") or f"단서 {order}"


def _block(game, viewer: int, block: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in block.items() if k != "항목"}
    kind = block.get("종류")
    if kind == "선택지":
        items = block.get("항목", [])
        out["항목"] = [_item(game, viewer, i, bool(block.get("소개보임"))) for i in items]
        player = game.players.get(viewer)
        picks_character = any(isinstance(i, Ref) and i.kind == "인물" for i in items)
        out["내_선택_끝남"] = bool(picks_character and player and player.character is not None)
    elif kind == "투표":
        player = game.players.get(viewer)
        mine = player.character if player else None
        raw = block.get("항목", [])
        items = [_item(game, viewer, i) for i in raw]
        for item, original in zip(items, raw):
            item.pop("선택한_계정", None)
            item["기타"] = not isinstance(original, Ref)                  # 인물·장소·단서가 아닌 선택지(예: 사고사)
            item["종류"] = original.kind if isinstance(original, Ref) else "기타"
            if isinstance(original, Ref) and original.kind != "인물":
                item["값"] = _vote_value(original)
                item["이름"] = clues.place_path(game, original.key) if original.kind == "장소" else _clue_label(game, original.key)
                for extra in ("유형", "특징"):
                    item.pop(extra, None)
            item["비활성"] = player is None or (mine is not None and item["값"] == mine)   # 관전자는 고르지 못하고 자기 인물에게는 투표할 수 없다
        out["항목"] = items
        out["내_선택"] = game.votes.get(block["이름"], {}).get(viewer)
        out["투표수"] = len(game.votes.get(block["이름"], {}))
    elif kind == "카드목록":
        out["항목"] = list(block.get("항목", []))
    elif kind == "읽기":
        record = game.reads.get(block["질문ID"], {"필요": set(), "확인": set()})
        out["확인함"] = viewer in record["확인"]
        out["확인필요"] = viewer in record["필요"] and viewer not in record["확인"]
        out["현황"] = {"완료": len(record["확인"] & record["필요"]), "전체": len(record["필요"])}
    return out


def card_view(game, viewer: int) -> dict[str, Any]:
    """`viewer` 에게 보여도 되는 화면 블록·탭·알림·오류. 다른 플레이어에게만 보이도록 한 것은 들어가지 않는다."""
    screens: list[dict[str, Any]] = []
    for run in game.runs.values():
        shown: dict[str, dict[str, Any]] = {}
        for target in (ALL, viewer):          # 같은 이름이면 나에게만 보이도록 한 것이 모두에게 보이는 것을 대신한다(자리는 그대로)
            for name, block in run.screens.get(target, {}).items():
                shown[name] = block
        for block in shown.values():
            screens.append({"카드": run.title, **_block(game, viewer, block)})
    merged: dict[str, dict[str, Any]] = {}
    for target in (ALL, viewer):
        for name, tab in game.tabs.get(target, {}).items():
            if tab["유지"] or tab["위치"] == game.phase_index:
                merged[name] = tab
    tabs = []
    for name, tab in sorted(merged.items(), key=lambda kv: kv[1]["순번"]):
        shown = {**_block(game, viewer, tab["내용"]), "이름": name, "카드": tab["카드"]}
        if tab["카드"] not in game.runs or (viewer not in game.players):
            shown.pop("동작", None)                  # 이전 단계에서 남은 탭의 버튼은 더 이상 받지 않는다(관전자에게도 없다)
            shown.pop("질문ID", None)
        tabs.append(shown)
    errors = []
    if viewer in (game.host_id, game.authority_id):
        errors = [{"카드": r.title, "메시지": r.error} for r in game.runs.values() if r.error]
    return {"화면": screens, "탭": tabs, "알림": list(game.notices.get(viewer, [])), "오류": errors}
