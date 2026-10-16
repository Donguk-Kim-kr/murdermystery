import { describe, expect, it } from "vitest";

import { EDGE, hitTest, type TileBox } from "./flowDrag";

// 폭 200 인 카드 셋을 간격 10 으로 놓은 흐름: [0,200] [210,410] [420,620]
const tiles: TileBox[] = [
  { order: 5, left: 0, right: 200 },
  { order: 6, left: 210, right: 410 },
  { order: 9, left: 420, right: 620 },
];
const flow = { left: 0, right: 620, top: 100, bottom: 200 };
const base = { tiles, flow, slot: null };

describe("hitTest", () => {
  it("흐름 줄에서 한참 벗어나면 어디에도 놓지 않는다", () => {
    expect(hitTest({ ...base, canAttach: true, x: 100, y: 400 })).toBeNull();
    expect(hitTest({ ...base, canAttach: true, x: 100, y: 20 })).toBeNull();
    expect(hitTest({ ...base, canAttach: true, x: 100, y: 190 })).not.toBeNull();
    expect(hitTest({ ...base, canAttach: true, x: 100, y: 215 })).not.toBeNull();   // 줄 아래 약간은 여전히 흐름 위
  });

  it("카드 안쪽은 붙이기, 가장자리는 앞뒤 자리 열기", () => {
    expect(hitTest({ ...base, canAttach: true, x: 300, y: 150 })).toEqual({ type: "attach", order: 6 });
    expect(hitTest({ ...base, canAttach: true, x: 210 + EDGE - 1, y: 150 })).toEqual({ type: "slot", index: 1 });
    expect(hitTest({ ...base, canAttach: true, x: 410 - EDGE + 1, y: 150 })).toEqual({ type: "slot", index: 2 });
  });

  it("페이즈 카드를 끌 때는 붙이기가 없고 왼쪽 절반은 앞, 오른쪽 절반은 뒤", () => {
    expect(hitTest({ ...base, canAttach: false, x: 300, y: 150 })).toEqual({ type: "slot", index: 1 });   // 6번 칸의 왼쪽 절반
    expect(hitTest({ ...base, canAttach: false, x: 350, y: 150 })).toEqual({ type: "slot", index: 2 });
    expect(hitTest({ ...base, canAttach: false, x: 10, y: 150 })).toEqual({ type: "slot", index: 0 });
    expect(hitTest({ ...base, canAttach: false, x: 610, y: 150 })).toEqual({ type: "slot", index: 3 });
  });

  it("카드 사이 틈과 양끝 바깥은 가까운 쪽에 자리를 연다", () => {
    expect(hitTest({ ...base, canAttach: true, x: 205, y: 150 })).toEqual({ type: "slot", index: 1 });      // 1번과 2번 사이
    expect(hitTest({ ...base, canAttach: true, x: -30, y: 150 })).toEqual({ type: "slot", index: 0 });
    expect(hitTest({ ...base, canAttach: true, x: 700, y: 150 })).toEqual({ type: "slot", index: 3 });
  });

  it("열린 빈자리 안에 있으면 그대로 둔다(뒤집히지 않는다)", () => {
    // 1번과 2번 사이에 폭 56 의 자리가 열려 뒤의 카드들이 밀린 상태
    const shifted: TileBox[] = [
      { order: 5, left: 0, right: 200 },
      { order: 6, left: 276, right: 476 },
      { order: 9, left: 486, right: 686 },
    ];
    const slot = { index: 1, left: 210, right: 266 };
    expect(hitTest({ canAttach: true, x: 240, y: 150, tiles: shifted, flow, slot })).toEqual({ type: "slot", index: 1 });
    // 밀려난 카드의 왼쪽 가장자리도 같은 틈이므로 열린 자리가 유지된다
    expect(hitTest({ canAttach: true, x: 276 + 4, y: 150, tiles: shifted, flow, slot })).toEqual({ type: "slot", index: 1 });
    // 안쪽으로 들어가면 붙이기로 바뀐다
    expect(hitTest({ canAttach: true, x: 380, y: 150, tiles: shifted, flow, slot })).toEqual({ type: "attach", order: 6 });
  });

  it("카드가 하나도 없으면 맨 앞 자리", () => {
    expect(hitTest({ canAttach: true, x: 50, y: 150, tiles: [], flow, slot: null })).toEqual({ type: "slot", index: 0 });
  });
});
