"""조사: 장소에서 단서와 증언을 얻는다 (docs/ENGINE_DESIGN.md 1-2, 조사 단계의 결정).

* 조사 단위는 가장 안쪽 장소(자식 장소가 없는 장소)이다.
* 장소를 한 번 고르면 **남은 항목 하나**를 얻는다. 무작위는 없다. 단서(한 명만 보유, 선착순)를 단서 순서대로 먼저 주고,
  단서가 남지 않았으면 이 플레이어가 아직 얻지 못한 증언(여러 명이 각자 얻을 수 있다)을 증언 순서대로 준다.
* 주는 것이 없으면 그 장소는 이 플레이어에게 비활성이다(남은 단서가 없는 장소가 비활성이라는 기본 규칙).
* 선택은 바로 반영된다. 같은 순간에 같은 단서를 두 사람이 고르면 먼저 처리된 사람이 얻고, 진 사람은 다음 항목을 얻거나 얻지 못한다.
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


def investigate(game, account: int, place_slot: int, io) -> dict[str, Any] | None:
    """장소를 조사해 항목 하나를 얻는다. 얻은 것을 돌려주고, 얻을 것이 없으면 None. 호출하는 쪽이 `game.lock` 을 잡는다."""
    if place_slot not in {p["순서"] for p in leaf_places(game)}:
        return None
    found = next_item(game, account, place_slot)
    if found is None:
        return None
    kind, row = found
    slot = game.phase["순서"]
    io.acquire(account, kind, row["순서"], slot, "조사")           # 기록을 먼저 남기고, 실패하면 메모리는 바뀌지 않는다
    game.holdings.setdefault(account, []).append({"종류": kind, "순서": row["순서"], "방법": "조사", "위치": slot, "보유": True})
    return describe(game, kind, row)


def describe(game, kind: str, row: dict[str, Any]) -> dict[str, Any]:
    place = place_path(game, row["장소_순서"]) if row.get("장소_순서") is not None else ""
    if kind == "단서":
        return {"종류": "단서", "이름": row.get("이름") or "", "내용": row.get("내용") or "", "장소": place}
    return {"종류": "증언", "이름": f"{row.get('화자') or ''}의 증언", "내용": row.get("내용") or "", "장소": place}


def holdings_of(game, account: int) -> list[dict[str, Any]]:
    """이 플레이어가 지금 가진 항목(얻은 순서)."""
    out = []
    for h in game.holdings.get(account, []):
        if not h["보유"]:
            continue
        row = next((r for r in _rows(game, h["종류"]) if r["순서"] == h["순서"]), None)
        if row is not None:
            out.append(describe(game, h["종류"], row))
    return out
