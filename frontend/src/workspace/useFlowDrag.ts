import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type RefObject } from "react";

import { hitTest, type Hit, type TileBox } from "./flowDrag";

/** 끌 수 있는 것. 페이즈 카드, 새 페이즈 카드, 진행단계·기믹 카드(카드 상자), 페이즈 안에 붙은 진행단계·기믹. */
export type Payload =
  | { kind: "phase"; order: number; index: number }
  | { kind: "newphase" }
  | { kind: "step"; id: number }
  | { kind: "gimmick"; id: number }
  | { kind: "chip-step"; id: number; from: number }
  | { kind: "chip-gimmick"; id: number; from: number };

export interface DragView {
  payload: Payload;
  hover: Hit;
}

const THRESHOLD = 5;   // 이만큼(px) 움직이기 전에는 끌기가 아니라 누르기(클릭)로 본다
const ATTACHABLE = new Set<Payload["kind"]>(["step", "gimmick", "chip-step", "chip-gimmick"]);

/**
 * 마우스로 누른 채 끄는 동작(포인터 이벤트). 누른 카드 자체가 포인터를 따라 움직이고(복제본을 띄움),
 * 포인터가 올라간 위치에 따라 흐름의 모양이 바뀐다(빈자리가 열리거나 붙일 페이즈가 강조된다).
 * 움직이지 않고 떼면 클릭으로 본다.
 */
export function useFlowDrag(
  flowRef: RefObject<HTMLElement | null>,
  handlers: { onDrop: (p: Payload, hit: Hit) => void; onClick: (p: Payload) => void },
) {
  const [view, setView] = useState<DragView | null>(null);
  const latest = useRef(handlers);
  useEffect(() => {
    latest.current = handlers;
  });
  const cleanup = useRef<(() => void) | null>(null);
  useEffect(() => () => cleanup.current?.(), []);

  const press = useCallback(
    (e: ReactPointerEvent<HTMLElement>, payload: Payload) => {
      if (e.button !== 0 || e.isPrimary === false) return;
      if ((e.target as HTMLElement).closest("button, input, select, textarea, a, label")) return;
      e.stopPropagation(); // 안쪽 카드가 먼저 눌렸으면 바깥 카드는 시작하지 않는다
      cleanup.current?.();

      const el = e.currentTarget;
      const rect = el.getBoundingClientRect();
      const startX = e.clientX;
      const startY = e.clientY;
      const grabX = startX - rect.left;
      const grabY = startY - rect.top;
      let active = false;
      let hover: Hit = null;
      let ghost: HTMLElement | null = null;

      const measure = (x: number, y: number): Hit => {
        const flow = flowRef.current;
        if (!flow) return null;
        const fr = flow.getBoundingClientRect();
        const tiles: TileBox[] = [...flow.querySelectorAll<HTMLElement>("[data-tile]")]
          .filter((t) => !(payload.kind === "phase" && Number(t.dataset.order) === payload.order))
          .map((t) => {
            const r = t.getBoundingClientRect();
            return { order: Number(t.dataset.order), left: r.left, right: r.right };
          });
        const slotEl = flow.querySelector<HTMLElement>("[data-slot]");
        const sr = slotEl?.getBoundingClientRect();
        return hitTest({
          canAttach: ATTACHABLE.has(payload.kind),
          x,
          y,
          tiles,
          flow: { left: fr.left, right: fr.right, top: fr.top, bottom: fr.bottom },
          slot: slotEl && sr ? { index: Number(slotEl.dataset.index), left: sr.left, right: sr.right } : null,
        });
      };

      const setHover = (next: Hit) => {
        if (JSON.stringify(next) === JSON.stringify(hover)) return;
        hover = next;
        setView({ payload, hover });
      };

      const end = () => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onCancel);
        ghost?.remove();
        ghost = null;
        document.body.classList.remove("flow-dragging");
        cleanup.current = null;
      };

      const onMove = (ev: PointerEvent) => {
        if (!active) {
          if (Math.hypot(ev.clientX - startX, ev.clientY - startY) < THRESHOLD) return;
          active = true;
          ghost = el.cloneNode(true) as HTMLElement;
          ghost.classList.add("drag-ghost");
          ghost.removeAttribute("id");
          ghost.removeAttribute("aria-label");
          ghost.removeAttribute("data-tile");
          ghost.setAttribute("aria-hidden", "true");   // 따라다니는 복제본은 보조기기에 읽히지 않는다
          Object.assign(ghost.style, { width: `${rect.width}px`, height: `${rect.height}px` });
          document.body.appendChild(ghost);
          document.body.classList.add("flow-dragging");
          // 페이즈 카드는 흐름에서 빠지므로, 처음 빈자리는 원래 자리에 둔다
          hover = payload.kind === "phase" ? { type: "slot", index: payload.index } : null;
          setView({ payload, hover });
        }
        if (ghost) ghost.style.transform = `translate(${ev.clientX - grabX}px, ${ev.clientY - grabY}px)`;
        const flow = flowRef.current;
        if (flow) {
          const fr = flow.getBoundingClientRect();
          if (ev.clientY >= fr.top - 28 && ev.clientY <= fr.bottom + 28) {
            if (ev.clientX < fr.left + 48) flow.scrollLeft -= 14;
            else if (ev.clientX > fr.right - 48) flow.scrollLeft += 14;
          }
        }
        setHover(measure(ev.clientX, ev.clientY));
      };

      const onUp = () => {
        const wasActive = active;
        const finalHover = hover;
        end();
        if (wasActive) {
          setView(null);
          latest.current.onDrop(payload, finalHover);
        } else {
          latest.current.onClick(payload);
        }
      };

      const onCancel = () => {
        end();
        setView(null);
      };

      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onCancel);
      cleanup.current = end;
    },
    [flowRef],
  );

  return { view, press };
}
