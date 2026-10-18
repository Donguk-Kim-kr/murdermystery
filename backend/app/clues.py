"""조사: 장소에 있는 단서와 증언 중 **하나를 직접 골라** 얻는다 (docs/ENGINE_DESIGN.md 1-2, 조사 단계의 결정, 사용자 2026-10-18).

* 장소를 고르면 그 장소의 아무 항목이 나오는 것이 아니라, 장소마다 놓인 단서·증언이 목록으로 보이고 **그중 하나를 골라** 얻는다.
  장소가 있는 단서·증언(`장소_순서`)만 조사로 얻을 수 있다. 목록에는 남들에게 보이는 이름(`공개이름`)이 나온다.
* 단서는 한 명만 보유할 수 있어 **먼저 가져간 사람이 있으면 그 항목은 회색(고를 수 없음)** 이 된다(내가 얻은 것도 회색). 증언은 여러 명이 각자 얻을 수 있고 내가 이미 얻은 것만 회색이다.
* 선택은 바로 반영된다. 같은 순간에 같은 단서를 두 사람이 고르면 먼저 처리된 사람이 얻고, 진 사람은 얻지 못한다(횟수도 쓰지 않는다).
* 얻은 기록은 `획득` 에 남기고(`GameIO.acquire`), 보유 상태는 메모리의 `Game.holdings` 에 둔다.
"""
from typing import Any


def _rows(game, key: str) -> list[dict[str, Any]]:
    return sorted(game.snapshot.get(key) or [], key=lambda r: r["순서"])


def leaf_places(game) -> list[dict[str, Any]]:
    places = _rows(game, "장소")
    parents = {p.get("상위_장소_순서") for p in places}
    return [p for p in places if p["순서"] not in parents]


def place_path(game, slot: int) -> str:
    """"저택 › 서재" 처럼 위에서부터 이어 붙인 이름. 상위가 없으면 이름만."""
    by_slot = {p["순서"]: p for p in _rows(game, "장소")}
    names: list[str] = []
    seen: set[int] = set()
    cur = by_slot.get(slot)
    while cur is not None and cur["순서"] not in seen:
        seen.add(cur["순서"])
        names.append(cur["이름"])
        cur = by_slot.get(cur.get("상위_장소_순서"))
    return " › ".join(reversed(names))


def held(game, account: int, kind: str, order: int) -> bool:
    return any(h["종류"] == kind and h["순서"] == order and h["보유"] for h in game.holdings.get(account, []))


def clue_taken(game, order: int) -> bool:
    return any(h["종류"] == "단서" and h["순서"] == order and h["보유"] for items in game.holdings.values() for h in items)


def next_item(game, account: int, place_slot: int) -> tuple[str, dict[str, Any]] | None:
    """이 플레이어가 이 장소에서 지금 얻을 항목. 없으면 None."""
    for clue in _rows(game, "단서"):
        if clue.get("장소_순서") == place_slot and not clue_taken(game, clue["순서"]):
            return "단서", clue
    for testimony in _rows(game, "증언"):
        if testimony.get("장소_순서") == place_slot and not held(game, account, "증언", testimony["순서"]):
            return "증언", testimony
    return None


KINDS = ("단서", "증언")


def investigable(game) -> list[tuple[str, dict[str, Any]]]:
    """조사로 얻을 수 있는 항목(장소가 있는 단서·증언). 장소 순서대로, 같은 장소에서는 단서가 먼저, 그다음 증언."""
    out = [(kind, row) for kind in KINDS for row in _rows(game, kind) if row.get("장소_순서") is not None]
    return sorted(out, key=lambda kr: (kr[1]["장소_순서"], KINDS.index(kr[0]), kr[1]["순서"]))


def parse_target(value: Any) -> tuple[str, int] | None:
    """플레이어가 보낸 값("단서:3" 같은 글, 또는 종류와 번호를 가진 `Ref`)을 (종류, 순서)로. 읽을 수 없으면 None."""
    if hasattr(value, "kind") and hasattr(value, "key"):
        return (value.kind, value.key) if value.kind in KINDS and isinstance(value.key, int) else None
    if not isinstance(value, str) or ":" not in value:
        return None
    kind, _, number = value.partition(":")
    if kind not in KINDS or not number.isdigit():
        return None
    return kind, int(number)


def availability(game, account: int, kind: str, order: int) -> str:
    """이 플레이어에게 이 항목이 어떤 상태인지: "가능" / "가져감"(다른 사람이 가진 단서) / "얻음"(내가 가진 것)."""
    if held(game, account, kind, order):
        return "얻음"
    if kind == "단서" and clue_taken(game, order):
        return "가져감"
    return "가능"


def holders(game, kind: str, order: int) -> list[int]:
    """이 항목을 지금 가진 계정들."""
    return [a for a, items in game.holdings.items() if any(h["종류"] == kind and h["순서"] == order and h["보유"] for h in items)]


def investigate(game, account: int, target: Any, io) -> dict[str, Any] | None:
    """고른 단서·증언 하나를 얻는다. 얻은 것을 돌려주고, 얻을 수 없으면 None. 호출하는 쪽이 `game.lock` 을 잡는다."""
    parsed = parse_target(target)
    if parsed is None:
        return None
    kind, order = parsed
    row = next((r for r in _rows(game, kind) if r["순서"] == order), None)
    if row is None or row.get("장소_순서") is None or availability(game, account, kind, order) != "가능":
        return None
    slot = game.phase["순서"]
    io.acquire(account, kind, row["순서"], slot, "조사")           # 기록을 먼저 남기고, 실패하면 메모리는 바뀌지 않는다
    game.holdings.setdefault(account, []).append({"종류": kind, "순서": row["순서"], "방법": "조사", "위치": slot, "보유": True})
    return describe(game, kind, row)


def describe(game, kind: str, row: dict[str, Any]) -> dict[str, Any]:
    """카드 하나. `공개이름` 은 남들에게 보이는 이름(비워 두었으면 진짜 이름), `이름` 은 진짜 이름이다."""
    place = place_path(game, row["장소_순서"]) if row.get("장소_순서") is not None else ""
    name = row.get("이름") or ""
    return {
        "종류": kind, "순서": row["순서"], "이름": name, "공개이름": row.get("공개이름") or name,
        "내용": row.get("내용") or "", "장소": place,
    }


def holdings_of(game, account: int) -> list[dict[str, Any]]:
    """이 플레이어가 지금 가진 항목(얻은 순서). 단서에는 지금 누구에게 공개했는지(`공개`)와 양도할 수 있는지가 붙는다."""
    out = []
    for h in game.holdings.get(account, []):
        if not h["보유"]:
            continue
        row = next((r for r in _rows(game, h["종류"]) if r["순서"] == h["순서"]), None)
        if row is None:
            continue
        item = describe(game, h["종류"], row)
        item["양도가능"] = h["종류"] == "단서"                  # 증언은 들은 기억이라 보여 주기·양도가 안 된다
        if h["종류"] == "단서":
            targets = game.reveals.get((account, h["순서"]), set())
            item["공개"] = "전체" if ALL in targets else sorted(t for t in targets if isinstance(t, int))
        out.append(item)
    return out


ALL = "전체"


def _holds_clue(game, account: int, order: int) -> bool:
    return held(game, account, "단서", order)


def transfer(game, giver: int, taker: int, order: int, io) -> bool:
    """단서를 바로 넘긴다(받는 사람의 수락은 필요 없다). 그 단서에 걸린 공개는 모두 사라진다. 호출하는 쪽이 `game.lock` 을 잡는다."""
    if giver == taker or taker not in game.players or giver not in game.players or not _holds_clue(game, giver, order):
        return False
    slot = game.phase["순서"]
    io.transfer(giver, taker, order, slot)
    for h in game.holdings.get(giver, []):
        if h["종류"] == "단서" and h["순서"] == order and h["보유"]:
            h["보유"] = False
    game.holdings.setdefault(taker, []).append({"종류": "단서", "순서": order, "방법": "양도", "위치": slot, "보유": True})
    game.reveals.pop((giver, order), None)
    return True


def set_reveal(game, owner: int, order: int, targets: Any, io) -> bool:
    """단서를 볼 수 있는 사람을 지정한다(바꾸어 놓는다). `targets` 는 "전체" 이거나 계정 번호들이고, 비우면 공개를 모두 취소한다."""
    if owner not in game.players or not _holds_clue(game, owner, order):
        return False
    if targets == ALL:
        wanted: set = {ALL}
    elif isinstance(targets, (list, tuple, set)):
        wanted = set()
        for t in targets:
            if not isinstance(t, int) or isinstance(t, bool) or t == owner or t not in game.players:
                return False
            wanted.add(t)
    else:
        return False
    current = game.reveals.get((owner, order), set())
    for token in sorted(current - wanted, key=str):
        io.unreveal(owner, order, None if token == ALL else token)
    for token in sorted(wanted - current, key=str):
        io.reveal(owner, order, None if token == ALL else token)
    if wanted:
        game.reveals[(owner, order)] = wanted
    else:
        game.reveals.pop((owner, order), None)
    return True


def revealed_to(game, viewer: int) -> list[dict[str, Any]]:
    """다른 사람이 나에게(또는 전체에게) 보여 준 단서. `주인` 은 보여 준 사람의 캐릭터 이름(아직 안 골랐으면 닉네임)."""
    by_slot = {c["순서"]: c for c in game.snapshot.get("인물") or []}
    out = []
    for (owner, order), targets in game.reveals.items():
        if owner == viewer or not (ALL in targets or viewer in targets):
            continue
        row = next((r for r in _rows(game, "단서") if r["순서"] == order), None)
        player = game.players.get(owner)
        if row is None or player is None:
            continue
        item = describe(game, "단서", row)
        character = by_slot.get(player.character)
        item["주인"] = character["이름"] if character else player.nickname
        out.append(item)
    return out
