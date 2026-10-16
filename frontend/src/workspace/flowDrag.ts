/**
 * 흐름 위에서 끌고 있는 것이 어디에 놓이는지 판단한다(화면 요소와 무관한 순수 함수라 따로 시험한다).
 *
 * 입력은 지금 화면에 그려진 페이즈 카드들의 위치(끌고 있는 카드와 열려 있는 빈자리는 뺀다)와 포인터 위치이다.
 *  - attach : 그 페이즈에 붙인다(진행단계·기믹 카드만).
 *  - slot   : 그 번호 앞에 새 페이즈 자리를 연다(0 은 맨 앞, 카드 수는 맨 뒤).
 *
 * 빈자리(slot)가 열리면 뒤의 카드들이 밀려나므로, 같은 자리에서 판정이 계속 뒤집히지 않게 다음을 지킨다.
 *  - 포인터가 열린 빈자리 안에 있으면 그대로 둔다.
 *  - 페이즈 카드를 끌 때는 카드의 왼쪽 절반이면 그 앞, 오른쪽 절반이면 그 뒤에 자리를 연다.
 *  - 진행단계·기믹을 끌 때는 카드 가장자리(EDGE)만 틈으로 보고 안쪽은 붙이기로 본다. 이때 열리는 자리를 좁게(카드보다 훨씬 좁게)
 *    해서, 자리가 닫히며 카드가 당겨져도 포인터가 계속 같은 카드 안에 남게 한다.
 */
export interface Box {
  left: number;
  right: number;
}
export interface TileBox extends Box {
  order: number;
}
export interface FlowBox extends Box {
  top: number;
  bottom: number;
}
export interface OpenSlot extends Box {
  index: number;
}
export type Hit = { type: "attach"; order: number } | { type: "slot"; index: number } | null;

export const EDGE = 16;      // 카드 가장자리를 틈으로 보는 폭(px)
const MARGIN_Y = 28;          // 흐름 줄 위아래로 이만큼까지는 여전히 흐름 위로 본다

export function hitTest(opts: {
  canAttach: boolean;
  x: number;
  y: number;
  tiles: TileBox[];
  flow: FlowBox;
  slot: OpenSlot | null;
}): Hit {
  const { canAttach, x, y, tiles, flow, slot } = opts;
  if (y < flow.top - MARGIN_Y || y > flow.bottom + MARGIN_Y) return null;
  if (slot && x >= slot.left && x <= slot.right) return { type: "slot", index: slot.index };
  if (tiles.length === 0) return { type: "slot", index: 0 };
  for (let i = 0; i < tiles.length; i++) {
    const t = tiles[i];
    if (x < t.left || x > t.right) continue;
    if (!canAttach) return { type: "slot", index: x < (t.left + t.right) / 2 ? i : i + 1 };
    if (x < t.left + EDGE) return { type: "slot", index: i };
    if (x > t.right - EDGE) return { type: "slot", index: i + 1 };
    return { type: "attach", order: t.order };
  }
  // 카드 사이 틈이거나 양끝 바깥: 오른쪽에서 가장 가까운 카드 앞에, 없으면 맨 뒤에 자리를 연다
  const next = tiles.findIndex((t) => t.left > x);
  return { type: "slot", index: next === -1 ? tiles.length : next };
}
