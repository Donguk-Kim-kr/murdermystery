"""개인 서사의 부분 나누기 (docs/ENGINE_DESIGN.md 1-4-6).

`인물.서사` 는 컬럼 하나이고, 서사를 여러 부분으로 나눌 때는 각 부분의 맨 앞에 표기 줄을 넣어 한 글로 합쳐 저장한다.

    @@MMPART:k3x9ab@@
    첫 번째 서사 본문…
    @@MMPART:q8m2zt@@
    두 번째 서사 본문…

* 표기 줄: 앞뒤 공백을 지운 줄 전체가 `@@MMPART:` + 영소문자·숫자 6자 + `@@` 일 때.
* 표기가 하나도 없는 글(옛 서사)은 부분 하나로 보고, 다음 저장 때 ID 를 붙인다.
* 본문 어느 줄에든 `@@MMPART:` 글자가 들어 있으면 저장을 거부한다.
* 글자 수: 서사 전체 10000자를 부분 수로 나눈(소수는 버림) 만큼이 부분 하나의 제한이다. 부분은 인물당 최대 5개.
* 서버가 부분 목록(ID, 본문)을 받아 글로 합치고, 화면은 표기를 보지 않는다. 읽을 때는 가능한 만큼 너그럽게 해석한다.
"""
import re
import secrets
from dataclasses import dataclass

MARK = "@@MMPART:"
LINE_RE = re.compile(r"^@@MMPART:([a-z0-9]{6})@@$")
ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
MAX_PARTS = 5
TOTAL_LIMIT = 10000


class NarrativeError(ValueError):
    """저장할 수 없는 서사. 메시지는 제작자에게 그대로 보여 줄 수 있다."""


@dataclass
class Part:
    id: str | None
    text: str


def part_limit(count: int) -> int:
    """부분이 `count` 개일 때 부분 하나의 글자 수 제한."""
    return TOTAL_LIMIT // max(count, 1)


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _trim(text: str) -> str:
    """앞뒤의 빈 줄(공백만 있는 줄 포함)을 지운다. 글 안쪽은 그대로 둔다."""
    lines = text.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def split(raw: str) -> list[Part]:
    """저장된 글을 부분 목록으로 나눈다. 표기가 없으면 부분 하나(ID 없음). 비어 있으면 빈 목록."""
    text = _normalize(raw or "")
    parts: list[Part] = []
    current: Part | None = None
    lead: list[str] = []
    for line in text.split("\n"):
        m = LINE_RE.match(line.strip())
        if m:
            if current is not None:
                current.text = _trim("\n".join(current_lines))
            elif _trim("\n".join(lead)):
                parts.append(Part(None, _trim("\n".join(lead))))     # 첫 표기 앞에 글이 있으면 ID 없는 부분으로 본다
            current = Part(m.group(1), "")
            current_lines: list[str] = []
            parts.append(current)
        elif current is not None:
            current_lines.append(line)
        else:
            lead.append(line)
    if current is not None:
        current.text = _trim("\n".join(current_lines))
    elif _trim("\n".join(lead)):
        parts.append(Part(None, _trim("\n".join(lead))))
    return parts


def new_id(taken: set[str]) -> str:
    while True:
        candidate = "".join(secrets.choice(ID_ALPHABET) for _ in range(6))
        if candidate not in taken:
            return candidate


def join(parts: list[Part]) -> str:
    """부분 목록을 검사하고 저장할 글로 합친다. ID 가 없는 부분에는 새 ID 를 붙인다(주어진 목록을 바꾸지 않는다). 문제가 있으면 `NarrativeError`."""
    cleaned = [Part(p.id, _trim(_normalize(p.text))) for p in parts]
    if len(cleaned) > MAX_PARTS:
        raise NarrativeError(f"서사는 인물마다 {MAX_PARTS}개까지만 나눌 수 있습니다")
    limit = part_limit(len(cleaned))
    ids: set[str] = set()
    for i, p in enumerate(cleaned, 1):
        if MARK in p.text:
            raise NarrativeError(f"서사 {i}에 예약된 표기({MARK})가 들어 있어 저장할 수 없습니다")
        if not p.text.strip():
            raise NarrativeError(f"서사 {i}이(가) 비어 있습니다")
        if len(p.text) > limit:
            raise NarrativeError(f"서사 {i}이(가) 너무 깁니다({len(p.text)}자, 서사가 {len(cleaned)}개이면 각 {limit}자까지)")
        if p.id is not None:
            if not re.fullmatch(r"[a-z0-9]{6}", p.id):
                raise NarrativeError(f"서사 {i}의 ID 가 올바르지 않습니다")
            if p.id in ids:
                raise NarrativeError(f"서사 {i}의 ID 가 다른 서사와 겹칩니다")
            ids.add(p.id)
    lines: list[str] = []
    for p in cleaned:
        pid = p.id or new_id(ids)
        ids.add(pid)
        lines.append(f"{MARK}{pid}@@")
        lines.append(p.text)
    return "\n".join(lines)


def check_fits(parts: list[Part]) -> list[str]:
    """부분 수가 늘어 기존 글이 새 제한을 넘는 부분의 번호(1부터)를 돌려준다. 편집기가 "서사 추가하기" 전에 알리는 데 쓴다."""
    limit = part_limit(len(parts))
    return [i for i, p in enumerate(parts, 1) if len(p.text) > limit]


def numbered(raw: str, numbers: list[int]) -> str:
    """번호(1부터)로 고른 부분들을 번호 순서로 이어 붙인다(서사 1·2 를 고르면 1 뒤에 2). 없는 번호는 건너뛴다."""
    parts = split(raw)
    chosen = [parts[n - 1].text for n in sorted(set(numbers)) if isinstance(n, int) and 1 <= n <= len(parts)]
    return "\n\n".join(chosen)
