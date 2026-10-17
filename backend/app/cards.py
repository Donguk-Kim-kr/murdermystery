"""카드(진행단계를 페이즈에 놓은 것)의 실행: 스크립트를 게임에 붙인다 (docs/ENGINE_SPEC.md).

* 페이즈가 시작되면 그 페이즈의 카드마다 라이브러리 진행단계의 `규칙`(`{"스크립트": "…"}`)을 읽어 `실행(카드)` 를 시작한다.
* 스크립트가 `기다리기(종류)` 를 만나면 멈추고, 플레이어의 입력(`answer`)이 오면 이어서 실행한다. 한 번의 실행은 `game.lock` 안에서
  끝까지(또는 다음 대기까지) 돌아서, 입력은 한 번에 하나씩 처리된다.
* 스크립트가 하는 일은 모두 엔진 함수(`CardHost`)를 거친다. 상태를 바꾸고 권한을 확인하는 것은 엔진이다.
* 화면 요청(`보이기`, `탭`, `알림`, `읽기`)은 게임에 쌓아 두었다가 `card_view` 가 보는 사람에게 허용된 것만 골라 돌려준다.
"""
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from . import narrative
from .script import VM, Program, Ref, ScriptError, Suspend, builtin_names, compile_source

MAX_ANSWER_BYTES = 2000
MAX_NOTICES = 20
ALL = "모두"
PUBLIC_FIELDS = ("이름", "직업", "나이", "성별")
CHARACTER_FIELDS = ("이름", "직업", "나이", "성별", "타임라인", "능력", "비밀", "목표", "범인", "NPC")


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

MUTATING = {"배정", "읽기", "기다리기", "단계_끝내기", "게임_종료"}
FUNCTION_NAMES = {
    "플레이어들", "플레이어수", "인물들", "공통스토리", "서사들", "배정된_플레이어수", "인물_없는_플레이어가_있다",
    "글", "선택지", "현황", "거부", "배정", "읽기", "기다리기", "단계_끝내기", "게임_종료",
}
CONSTANT_NAMES = {"통과", ALL}


def known_names() -> set[str]:
    return FUNCTION_NAMES | CONSTANT_NAMES | builtin_names()


class CardHost:
    def __init__(self, game, run: CardRun, io, readonly: bool = False):
        self.game, self.run, self.io, self.readonly = game, run, io, readonly
        self.constants = {"통과": True, ALL: Ref(ALL)}
        self.functions: dict[str, Callable[..., Any]] = {}
        for name in FUNCTION_NAMES:
            self.functions[name] = self._guard(name, getattr(self, "fn_" + name))

    def _guard(self, name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        if name not in MUTATING:
            return fn

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

    def fn_공통스토리(self) -> str:
        return ((self.game.snapshot.get("작품") or {}).get("공통스토리")) or ""

    def fn_서사들(self, character: Any, numbers: Any) -> str:
        if character is None:
            return ""
        slot = self._character_slot(character)
        row = self._character(slot)
        if not isinstance(numbers, (list, tuple)):
            raise ScriptError("서사들() 의 두 번째 값은 번호 목록이어야 합니다(예: [1, 2])")
        return narrative.numbered(row.get("서사") or "", list(numbers))

    def fn_배정된_플레이어수(self) -> int:
        return sum(1 for p in self.game.players.values() if p.character is not None)

    def fn_인물_없는_플레이어가_있다(self) -> bool:
        return any(p.character is None for p in self.game.players.values())

    # -- 블록 만들기 --
    def fn_글(self, content: Any, name: str = "글") -> dict[str, Any]:
        return {"종류": "글", "이름": str(name), "내용": _text(content)}

    def fn_선택지(self, name: str, items: Any, 한사람당: int = 1, 확인필요: bool = False) -> dict[str, Any]:
        if not isinstance(items, (list, tuple)):
            raise ScriptError("선택지의 항목은 목록이어야 합니다")
        return {
            "종류": "선택지", "이름": str(name), "항목": list(items), "한사람당": 한사람당, "확인필요": bool(확인필요),
            "질문ID": f"{self.run.key}:확인",
        }

    def fn_현황(self, name: str, 완료: int, 전체: int) -> dict[str, Any]:
        return {"종류": "현황", "이름": str(name), "완료": int(완료), "전체": int(전체)}

    def fn_거부(self, message: Any) -> dict[str, Any]:
        return {"거부": _text(message)}

    # -- 엔진 명령 --
    def fn_배정(self, player: Any, character: Any) -> bool:
        from .engine import AssignError, assign_character

        account = self._player_account(player)
        slot = self._character_slot(character)
        try:
            assign_character(self.game, account, slot, lambda a, s: self.io.assign(a, s))
        except AssignError:
            return False
        return True

    def fn_읽기(self, target: Any, name: str, content: Any) -> None:
        accounts = self._target_accounts(target)
        qid = f"{self.run.key}:읽기:{name}"
        record = self.game.reads.setdefault(qid, {"필요": set(), "확인": set()})
        record["필요"].update(accounts)
        block = {"종류": "읽기", "이름": str(name), "내용": _text(content), "질문ID": qid}
        for key in ([ALL] if target.kind == ALL else [target.key]):
            self.run.screens.setdefault(key, {})[str(name)] = block

    def fn_기다리기(self, kind: str) -> Any:
        raise Suspend({"종류": str(kind)})

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
            if name in CHARACTER_FIELDS:
                return row.get(name)
        elif ref.kind == "카드":
            if name == "설정":
                return json.loads(json.dumps(self.run.settings))     # 스크립트가 바꿔도 원본은 그대로
            if name == "이름":
                return self.run.library.get("이름")
            if name == "표시이름":
                return self.run.title
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
            raise ScriptError("보이기() 에는 글(), 선택지(), 현황() 같은 블록을 넘겨야 합니다")
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
    if vm is None or vm.waiting is None or vm.waiting.get("종류") != rest:
        raise AnswerError("stale", "지금은 받지 않는 질문입니다")
    vm.host.io = io                                  # 기록은 이 요청의 연결로 쓴다(시작 때의 연결은 이미 닫혔다)
    vm.resume({"플레이어": Ref("플레이어", account_id), "값": value, "종류": rest})
    _run(game, run)
    pump_end_requests(game, io)
    game.bump()


# ---- 보는 사람에게 보여 줄 것 ----------------------------------------------------------------------

def _item(game, item: Any) -> dict[str, Any]:
    if isinstance(item, Ref) and item.kind == "인물":
        row = next((c for c in game.snapshot.get("인물") or [] if c["순서"] == item.key), None)
        taken = next((p.account_id for p in game.players.values() if p.character == item.key), None)
        return {"값": item.key, **{f: (row or {}).get(f) for f in PUBLIC_FIELDS}, "선택한_계정": taken}
    if isinstance(item, Ref):
        return {"값": None, "이름": item.kind}
    return {"값": item, "이름": str(item)}


def _block(game, viewer: int, block: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in block.items() if k != "항목"}
    kind = block.get("종류")
    if kind == "선택지":
        out["항목"] = [_item(game, i) for i in block.get("항목", [])]
        player = game.players.get(viewer)
        out["내_선택_끝남"] = bool(player and player.character is not None)
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
        for target in (ALL, viewer):
            for block in run.screens.get(target, {}).values():
                screens.append({"카드": run.title, **_block(game, viewer, block)})
    merged: dict[str, dict[str, Any]] = {}
    for target in (ALL, viewer):
        for name, tab in game.tabs.get(target, {}).items():
            if tab["유지"] or tab["위치"] == game.phase_index:
                merged[name] = tab
    tabs = [
        {**_block(game, viewer, tab["내용"]), "이름": name, "카드": tab["카드"]}
        for name, tab in sorted(merged.items(), key=lambda kv: kv[1]["순번"])
    ]
    errors = []
    if viewer in (game.host_id, game.authority_id):
        errors = [{"카드": r.title, "메시지": r.error} for r in game.runs.values() if r.error]
    return {"화면": screens, "탭": tabs, "알림": list(game.notices.get(viewer, [])), "오류": errors}
