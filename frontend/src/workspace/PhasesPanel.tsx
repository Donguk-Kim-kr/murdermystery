import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { errorMessage, http } from "../api/client";
import type { Hit } from "./flowDrag";
import { useFlowDrag, type Payload } from "./useFlowDrag";
import { phaseLabel, rowsOf, useWorkspace, type LibraryRef, type Row, type Workspace } from "./workspace";

export interface LibraryItem {
  번호: number;
  이름: string;
  버전: number;
  설명: string | null;
  변경내역: string | null;
  공통: boolean;
}

const pad = (n: number) => String(n).padStart(2, "0");

type Call = (method: string, path: string, body?: unknown) => Promise<boolean>;

/** 칸에 놓은 카드·기믹의 세부 설정(`설정`)에서 다음 페이즈에도 탭을 남길지를 가리키는 키. 이름은 임시이며 엔진 설계에서 확정한다. */
const KEEP_TAB = "탭유지";

/**
 * 게임 흐름 화면: 맨 위에 페이즈 카드가 왼쪽에서 오른쪽으로 놓이고, 아래에 진행카드(불러온 진행단계·기믹)가 있다.
 *  - 카드를 어디서든 누른 채 끌면 그 카드 자체가 움직이고, 올려 둔 자리에 따라 흐름의 모양이 바뀐다.
 *  - 진행카드를 페이즈 위에 놓으면 붙고, 페이즈 사이에 놓으면 새 페이즈로 끼워 넣는다. 페이즈 카드는 끌어서 순서를 바꾼다.
 *  - 페이즈 카드를 한 번 누르면 아래에서 이름·시간 등을 수정한다.
 * 서버가 칸의 내용을 옮기므로 붙여 둔 카드·기믹은 페이즈를 따라간다.
 */
export function PhasesPanel({ workId }: { workId: number }) {
  const { ws, error } = useWorkspace(workId);
  const [phaseItems, setPhaseItems] = useState<LibraryItem[]>([]);
  const [gimmickItems, setGimmickItems] = useState<LibraryItem[]>([]);

  useEffect(() => {
    void (async () => {
      const [p, g] = await Promise.all([
        http<LibraryItem[]>("GET", "/api/library/phases"),
        http<LibraryItem[]>("GET", "/api/library/gimmicks"),
      ]);
      setPhaseItems(p.data ?? []);
      setGimmickItems(g.data ?? []);
    })();
  }, []);

  if (error) return <p role="alert" className="error">{error}</p>;
  if (!ws) return <p className="center">불러오는 중…</p>;
  return <PhasesBody workId={workId} ws={ws} phaseItems={phaseItems} gimmickItems={gimmickItems} />;
}

/** 이 작품 흐름 아래에 불러와 둔 진행카드. 화면 편의일 뿐이라 브라우저에만 기억한다. */
function useTray(workId: number) {
  const key = `mm.tray.${workId}`;
  const read = (): { steps: number[]; gimmicks: number[] } => {
    try {
      const v = JSON.parse(localStorage.getItem(key) ?? "null") as { steps?: number[]; gimmicks?: number[] } | null;
      return { steps: v?.steps ?? [], gimmicks: v?.gimmicks ?? [] };
    } catch {
      return { steps: [], gimmicks: [] };
    }
  };
  const [tray, setTray] = useState(read);
  const update = (next: { steps: number[]; gimmicks: number[] }) => {
    setTray(next);
    try {
      localStorage.setItem(key, JSON.stringify(next));
    } catch {
      /* 기억하지 못해도 이번 화면에서는 쓸 수 있다 */
    }
  };
  const toggle = (kind: "steps" | "gimmicks", id: number) =>
    update({ ...tray, [kind]: tray[kind].includes(id) ? tray[kind].filter((x) => x !== id) : [...tray[kind], id] });
  return { tray, toggle };
}

function PhasesBody({ workId, ws, phaseItems, gimmickItems }: {
  workId: number; ws: Workspace; phaseItems: LibraryItem[]; gimmickItems: LibraryItem[];
}) {
  const phases = rowsOf(ws, "phases");
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);   // 수정 패널에 열린 페이즈의 칸 번호
  const [vertical, setVertical] = useState(false);
  const [loader, setLoader] = useState(false);
  const flowRef = useRef<HTMLOListElement>(null);
  const { tray, toggle } = useTray(workId);
  const sel = phases.findIndex((p) => p.순서 === selected);

  /** 서버 호출. 실패하면 메시지를 보여 주고 undefined 를 돌려준다. */
  async function req<T = unknown>(method: string, path: string, body?: unknown): Promise<{ data: T } | undefined> {
    const url = path.startsWith("/") ? `/api/works/${workId}${path}` : `/api/works/${workId}/content/${path}`;
    const res = await http<T>(method, url, body);
    if (res.error) {
      setError(errorMessage(res.error, "처리하지 못했습니다"));
      return undefined;
    }
    return { data: res.data as T };
  }

  /** 서버 호출 뒤 작업공간을 다시 읽는다. path 가 "/" 로 시작하면 그대로, 아니면 콘텐츠 경로로 본다. */
  const call: Call = async (method, path, body) => {
    setError(null);
    const ok = (await req(method, path, body)) !== undefined;
    if (ok) await ws.reload();
    return ok;
  };

  /** 칸 slot 에 진행단계·기믹을 붙이거나, 붙어 있던 것을 옮긴다. */
  async function putInto(slot: number, p: Payload): Promise<boolean> {
    switch (p.kind) {
      case "step":
        return !!(await req("POST", "phase-steps", { 진행순서_순서: slot, 진행단계_번호: p.id }));
      case "gimmick":
        return !!(await req("POST", "gimmick-uses", { 진행순서_순서: slot, 기믹_번호: p.id }));
      case "chip-step":
        return p.from === slot || !!(await req("PATCH", `phase-steps/${p.id}`, { 진행순서_순서: slot }));
      case "chip-gimmick":
        return p.from === slot || !!(await req("PATCH", `gimmick-uses/${p.id}`, { 진행순서_순서: slot }));
      default:
        return false;
    }
  }

  async function onDrop(p: Payload, hit: Hit) {
    if (!hit) return;
    setError(null);
    if (hit.type === "attach") {
      await putInto(hit.order, p);
    } else if (p.kind === "phase") {
      // hit.index 는 끌고 있는 카드를 뺀 목록에서의 자리이다 → 옮길 위치(1부터)는 index + 1
      if (hit.index !== p.index) await req("POST", `/phases/${p.order}/move`, { position: hit.index + 1 });
    } else {
      const made = await req<{ phases: Row[] }>("POST", "/phases/insert", { position: hit.index + 1, 이름: null, 진행시간: 30 });
      if (made) await putInto(made.data.phases[hit.index].순서 as number, p);
    }
    await ws.reload();
  }

  const { view, press } = useFlowDrag(flowRef, {
    onDrop: (p, hit) => void onDrop(p, hit),
    onClick: (p) => {
      if (p.kind === "phase") setSelected(p.order);
      else if (p.kind === "chip-step" || p.kind === "chip-gimmick") setSelected(p.from);
    },
  });

  const dragging = view?.payload ?? null;
  const hover = view?.hover ?? null;
  const phaseDrag = dragging?.kind === "phase" ? dragging : null;
  const slotAt = hover?.type === "slot" ? hover.index : -1;
  const slotWide = phaseDrag !== null || phases.length === 0;   // 페이즈 카드를 끌 때(와 첫 페이즈)는 카드 폭의 빈자리, 진행카드를 끌 때는 좁은 빈자리
  // 끌고 있는 페이즈 카드는 제자리에 남아 빈자리 역할을 하다가, 다른 자리로 올리면 부드럽게 접히며 그쪽 빈자리가 열린다.
  const originCollapsed = phaseDrag !== null && slotAt !== -1 && slotAt !== phaseDrag.index;
  const empty = phases.length === 0;

  // 모든 틈에 빈자리를 두고(접힌 채로), 올려 둔 곳만 폭을 늘린다. 요소가 그대로라 CSS 전환으로 옆 카드들이 부드럽게 밀려난다.
  const items: React.ReactNode[] = [];
  let k = 0;   // 끌고 있는 카드를 뺀 순번
  phases.forEach((p, index) => {
    const origin = phaseDrag?.order === p.순서;
    if (!origin) {
      items.push(<Slot key={`slot-${k}`} index={k} open={slotAt === k && !(phaseDrag && k === phaseDrag.index)} wide={slotWide} />);
    }
    items.push(
      <PhaseTile key={String(p.순서)} ws={ws} phase={p} index={index} selected={p.순서 === selected}
        attach={hover?.type === "attach" && hover.order === p.순서} origin={origin} collapsed={origin && originCollapsed} press={press} />,
    );
    if (!origin) k++;
  });
  items.push(<Slot key={`slot-${k}`} index={k} open={slotAt === k && !(phaseDrag && k === phaseDrag.index)} wide={slotWide} />);

  return (
    <section className="card" aria-label="페이즈">
      <div className="row">
        <h2>게임 흐름 <span className="muted">(페이즈 {phases.length}개)</span></h2>
        <button type="button" className="small secondary" disabled={empty} onClick={() => setVertical(true)}>
          세로로 보기
        </button>
      </div>
      <ol className="flow" ref={flowRef} aria-label="게임 흐름">
        {items}
        {empty && !dragging && (
          <li className="flow-empty">아래 진행카드를 이곳으로 끌어다 놓으면 첫 페이즈가 만들어집니다.</li>
        )}
      </ol>
      {sel >= 0 && (
        <PhaseEditor ws={ws} phase={phases[sel]} index={sel} total={phases.length} call={call}
          onNavigate={(delta) => setSelected((phases[sel + delta]?.순서 as number | undefined) ?? selected)} onClose={() => setSelected(null)} />
      )}
      <TraySection ws={ws} phaseItems={phaseItems} gimmickItems={gimmickItems} tray={tray} press={press}
        onOpenLoader={() => setLoader(true)} onUnload={toggle} />
      {error && <p role="alert" className="error">{error}</p>}
      {vertical && <VerticalView ws={ws} onClose={() => setVertical(false)} />}
      {loader && <CardLoader phaseItems={phaseItems} gimmickItems={gimmickItems} tray={tray} onToggle={toggle} onClose={() => setLoader(false)} />}
    </section>
  );
}

type PressFn = (e: React.PointerEvent<HTMLElement>, payload: Payload) => void;

/** 틈마다 놓인 빈자리. 평소에는 폭 0 으로 접혀 있고, 끌고 있는 카드가 올라오면 부드럽게 폭이 늘어 옆 카드들을 밀어낸다.
 *  진행카드를 카드 사이에 놓을 때(좁은 빈자리)는 표시 없이 자리만 열린다. 페이즈 카드를 옮길 때(넓은 빈자리)는 놓일 자리를 점선으로 보여 준다. */
function Slot({ index, open, wide }: { index: number; open: boolean; wide: boolean }) {
  return (
    <li className={`flow-slot${open ? " open" : ""}${wide ? " wide" : ""}`} data-slot data-index={index} aria-hidden="true">
      {open && wide ? "여기에 놓기" : ""}
    </li>
  );
}

/** 세로로 훑어보는 읽기 전용 팝업(검토용). 편집은 가로 흐름에서 한다. */
function VerticalView({ ws, onClose }: { ws: Workspace; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label="세로로 보기" onClick={(e) => e.stopPropagation()}>
        <div className="row">
          <h2>게임 흐름 <span className="muted">(총 {totalMinutes(ws)}분)</span></h2>
          <button type="button" className="small secondary" onClick={onClose}>닫기</button>
        </div>
        <FlowVertical ws={ws} />
      </div>
    </div>
  );
}

const totalMinutes = (ws: Workspace) => rowsOf(ws, "phases").reduce((sum, p) => sum + Number(p.진행시간 ?? 0), 0);

/** 확인 탭에서 쓰는 세로 보기(읽기 전용): 게임 흐름을 위에서 아래로 보여 준다. */
export function FlowReview({ workId }: { workId: number }) {
  const { ws, error } = useWorkspace(workId);
  if (error) return <p role="alert" className="error">{error}</p>;
  if (!ws) return <p className="center">불러오는 중…</p>;
  return (
    <section className="card" aria-label="게임 흐름 세로 보기">
      <h2>게임 흐름 <span className="muted">(세로 보기 · 총 {totalMinutes(ws)}분)</span></h2>
      {rowsOf(ws, "phases").length === 0 ? <p className="muted">아직 페이즈가 없습니다.</p> : <FlowVertical ws={ws} />}
    </section>
  );
}

/** 페이즈를 위에서 아래로 늘어놓은 읽기 전용 목록. */
function FlowVertical({ ws }: { ws: Workspace }) {
  const phases = rowsOf(ws, "phases");
  const steps = rowsOf(ws, "phase-steps");
  const uses = rowsOf(ws, "gimmick-uses");
  return (
    <ol className="vertical">
      {phases.map((p, i) => {
        const mine = steps.filter((c) => c.진행순서_순서 === p.순서);
        const gim = uses.filter((u) => u.진행순서_순서 === p.순서);
        return (
          <li key={String(p.순서)}>
            <strong>{phaseTitle(p, i, mine)}</strong> <span className="muted">· {String(p.진행시간)}분</span>
            {mine.length + gim.length === 0 && <p className="muted">비어 있음</p>}
            <ul>
              {mine.map((c) => <li key={`s${c.번호}`}>{String(c.표시이름 ?? "진행단계")}{c.설정 != null && <span className="muted"> · 설정 있음</span>}</li>)}
              {gim.map((u) => (
                <li key={`g${u.순서}`}>
                  기믹 · {ws.bundle.library.gimmicks[String(u.기믹_번호)]?.이름 ?? `#${String(u.기믹_번호)}`}
                </li>
              ))}
            </ul>
          </li>
        );
      })}
    </ol>
  );
}

/** 페이즈 제목: 제작자가 정한 이름, 없으면 붙은 진행단계 이름을 이은 것(서버가 계산한 표시이름), 그것도 없으면 "이름 없음". */
function phaseTitle(phase: Row, index: number, cards: Row[]): string {
  const shown = typeof phase.표시이름 === "string" && phase.표시이름 !== "" ? phase.표시이름 : null;
  const fallback = cards.map((c) => String(c.표시이름 ?? "")).filter(Boolean).join("·");
  return `${index + 1}. ${shown ?? (fallback || "이름 없음")}`;
}

/** 진행카드 영역: 불러와 둔 진행단계·기믹 카드. 흐름에 끌어다 놓아 쓴다. */
function TraySection({ ws, phaseItems, gimmickItems, tray, press, onOpenLoader, onUnload }: {
  ws: Workspace; phaseItems: LibraryItem[]; gimmickItems: LibraryItem[];
  tray: { steps: number[]; gimmicks: number[] }; press: PressFn; onOpenLoader: () => void;
  onUnload: (kind: "steps" | "gimmicks", id: number) => void;
}) {
  void ws;
  const steps = tray.steps.map((id) => phaseItems.find((i) => i.번호 === id)).filter((i): i is LibraryItem => !!i);
  const gimmicks = tray.gimmicks.map((id) => gimmickItems.find((i) => i.번호 === id)).filter((i): i is LibraryItem => !!i);
  return (
    <section className="tray" aria-label="진행카드">
      <div className="row">
        <h3>진행카드</h3>
        <button type="button" className="small secondary" onClick={onOpenLoader}>진행카드 불러오기</button>
      </div>
      <ul className="tray-cards">
        {steps.map((i) => (
          <TrayCard key={`s${i.번호}`} item={i} label="진행단계" press={press} payload={{ kind: "step", id: i.번호 }}
            onUnload={() => onUnload("steps", i.번호)} />
        ))}
        {gimmicks.map((i) => (
          <TrayCard key={`g${i.번호}`} item={i} label="기믹" press={press} payload={{ kind: "gimmick", id: i.번호 }}
            onUnload={() => onUnload("gimmicks", i.번호)} />
        ))}
      </ul>
      {steps.length + gimmicks.length === 0 && <p className="muted">"진행카드 불러오기"로 라이브러리의 진행단계·기믹을 이곳에 꺼내 두세요.</p>}
    </section>
  );
}

function TrayCard({ item, label, payload, press, onUnload }: {
  item: LibraryItem; label: string; payload: Payload; press: PressFn; onUnload: () => void;
}) {
  return (
    <li className={`tray-card${payload.kind === "gimmick" ? " gimmick" : ""}`} aria-label={`${label} 카드 ${item.이름}`}
      onPointerDown={(e) => press(e, payload)}>
      <strong>{item.이름}</strong>
      {item.설명 && <span className="muted tray-desc">{item.설명}</span>}
      <button type="button" className="link tray-x" aria-label={`${item.이름} v${item.버전} 빼기`} onClick={onUnload}>×</button>
    </li>
  );
}

/** 라이브러리의 진행단계·기믹을 골라 진행카드로 불러온다. 많아져도 찾을 수 있게 이름으로 검색한다. */
function CardLoader({ phaseItems, gimmickItems, tray, onToggle, onClose }: {
  phaseItems: LibraryItem[]; gimmickItems: LibraryItem[]; tray: { steps: number[]; gimmicks: number[] };
  onToggle: (kind: "steps" | "gimmicks", id: number) => void; onClose: () => void;
}) {
  const [kind, setKind] = useState<"steps" | "gimmicks">("steps");
  const [query, setQuery] = useState("");
  const [tipOpen, setTipOpen] = useState<number | null>(null);   // 설명을 펼쳐 둔 카드(i 버튼)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const all = kind === "steps" ? phaseItems : gimmickItems;
  const shown = all.filter((i) => i.이름.includes(query.trim()));
  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label="진행카드 불러오기" onClick={(e) => { e.stopPropagation(); setTipOpen(null); }}>
        <div className="row">
          <h2>진행카드 불러오기</h2>
          <button type="button" className="small secondary" onClick={onClose}>닫기</button>
        </div>
        <div className="row start" role="tablist" aria-label="종류">
          <button type="button" role="tab" aria-selected={kind === "steps"} className={`tab${kind === "steps" ? " active" : ""}`}
            onClick={() => setKind("steps")}>진행단계</button>
          <button type="button" role="tab" aria-selected={kind === "gimmicks"} className={`tab${kind === "gimmicks" ? " active" : ""}`}
            onClick={() => setKind("gimmicks")}>기믹</button>
        </div>
        <input aria-label="이름 검색" placeholder="이름 검색" value={query} onChange={(e) => setQuery(e.target.value)} />
        {all.length === 0 && (
          <p className="muted">
            라이브러리에 {kind === "steps" ? "진행단계" : "기믹"}가 없습니다. <Link to="/make/library">라이브러리 만들기</Link>에서 먼저 만들어 주세요.
          </p>
        )}
        {all.length > 0 && shown.length === 0 && <p className="muted">찾는 이름이 없습니다.</p>}
        {/* 이름만 있는 카드를 격자로 늘어놓는다. 누르면 선택, 다시 누르면 해제(선택된 카드가 흐름 아래 진행카드에 놓인다).
            많아져도 한눈에 보이고, 마우스를 올리면(또는 포커스하면) 설명이 나온다 */}
        <ul className="loader-grid">
          {shown.map((i) => {
            const loaded = tray[kind].includes(i.번호);
            const sameName = all.filter((x) => x.이름 === i.이름).length > 1;   // 같은 이름의 다른 버전이 있을 때만 버전을 보여 구분한다
            const tip = [`v${i.버전}${i.공통 ? " · 공통" : ""}`, i.변경내역 ? `변경: ${i.변경내역}` : null, i.설명 || null].filter(Boolean).join("\n");
            const open = tipOpen === i.번호;
            return (
              <li key={i.번호} className="loader-item">
                <button type="button" className={`loader-card${loaded ? " loaded" : ""}`} aria-pressed={loaded}
                  aria-label={`${i.이름} v${i.버전}`} onClick={() => onToggle(kind, i.번호)}>
                  <strong>{i.이름}</strong>
                  {sameName && <span className="muted">v{i.버전}</span>}
                  {loaded && <span className="loader-check" aria-hidden="true">✓ 선택됨</span>}
                </button>
                {/* 카드 오른쪽 위의 i 버튼: 누르면 설명이 펼쳐지고, 다시 누르거나 다른 곳을 누르면 닫힌다 */}
                <button type="button" className="loader-info" aria-label={`${i.이름} v${i.버전} 설명 보기`} aria-expanded={open}
                  onClick={(e) => { e.stopPropagation(); setTipOpen(open ? null : i.번호); }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                    <circle cx="12" cy="12" r="9" /><path d="M12 11v5" /><path d="M12 8h.01" />
                  </svg>
                </button>
                {open && <span role="note" className="loader-tip">{tip}</span>}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

/** 흐름 위의 페이즈 카드: 번호(작은 숫자), 페이즈 이름, 붙은 진행단계, 시간. 어디를 눌러도 끌 수 있고, 한 번 누르면 수정 패널이 열린다. */
function PhaseTile({ ws, phase, index, selected, attach, origin, collapsed, press }: {
  ws: Workspace; phase: Row; index: number; selected: boolean; attach: boolean; origin: boolean; collapsed: boolean; press: PressFn;
}) {
  const no = phase.순서 as number;
  const steps = rowsOf(ws, "phase-steps").filter((s) => s.진행순서_순서 === no);
  const uses = rowsOf(ws, "gimmick-uses").filter((u) => u.진행순서_순서 === no);
  // 이름은 제작자가 정한 것, 없으면 붙은 진행단계 이름을 이은 것("조사·밀담"). 서버가 계산해 내려 준다.
  const name = typeof phase.표시이름 === "string" && phase.표시이름 !== "" ? phase.표시이름 : null;
  return (
    <li className={`phase tile${selected ? " selected" : ""}${attach ? " over" : ""}${origin ? " drag-origin" : ""}${collapsed ? " collapsed" : ""}`}
      data-tile data-order={no} aria-label={`페이즈 ${index + 1}`} aria-hidden={origin || undefined} tabIndex={origin ? -1 : 0}
      onPointerDown={(e) => press(e, { kind: "phase", order: no, index })}>
      <div className="tile-head">
        <span className="tile-no">{pad(index + 1)}</span>
        <span className="muted">{String(phase.진행시간)}분</span>
      </div>
      <strong className={`tile-name${name ? "" : " muted"}`}>{name ?? "이름 없음"}</strong>
      {steps.length + uses.length === 0 && <p className="muted tile-empty">진행단계 없음</p>}
      <ul className="chips">
        {steps.map((r) => <TileChip key={`s${r.번호}`} row={r} lib={ws.bundle.library.phases} libCol="진행단계_번호" step from={no} press={press} />)}
        {uses.map((r) => <TileChip key={`g${r.순서}`} row={r} lib={ws.bundle.library.gimmicks} libCol="기믹_번호" step={false} from={no} press={press} />)}
      </ul>
    </li>
  );
}

function TileChip({ row, lib, libCol, step, from, press }: {
  row: Row; lib: Record<string, LibraryRef>; libCol: string; step: boolean; from: number; press: PressFn;
}) {
  const ref = lib[String(row[libCol])];
  const id = (step ? row.번호 : row.순서) as number;
  const name = (step && typeof row.표시이름 === "string" ? row.표시이름 : ref?.이름) ?? `#${String(row[libCol])}`;
  return (
    <li className={`chip ${ref?.삭제됨 ? "danger" : step ? "accent" : ""}`}
      onPointerDown={(e) => press(e, step ? { kind: "chip-step", id, from } : { kind: "chip-gimmick", id, from })}>
      {!step && <span className="muted">기믹 </span>}{name}
      {ref?.삭제됨 && " · 삭제된 항목"}
      {row.설정 != null && <span className="dot" title="세부 설정 있음" aria-label="세부 설정 있음">●</span>}
    </li>
  );
}

/** 고른 페이즈의 수정 패널: 이름·시간, 이전/다음 페이즈로 넘어가기, 삭제, 붙은 진행단계·기믹 각각의 수정. */
function PhaseEditor({ ws, phase, index, total, call, onNavigate, onClose }: {
  ws: Workspace; phase: Row; index: number; total: number; call: Call; onNavigate: (delta: -1 | 1) => void; onClose: () => void;
}) {
  const no = phase.순서 as number;
  const [time, setTime] = useState(String(phase.진행시간));
  const [name, setName] = useState(typeof phase.이름 === "string" ? phase.이름 : "");
  // 다른 페이즈로 넘어가거나 끼워 넣기·옮기기로 서버 값이 바뀌면 입력칸도 맞춘다.
  useEffect(() => {
    setTime(String(phase.진행시간));
    setName(typeof phase.이름 === "string" ? phase.이름 : "");
  }, [no, phase.이름, phase.진행시간]);
  const steps = rowsOf(ws, "phase-steps").filter((s) => s.진행순서_순서 === no);
  const uses = rowsOf(ws, "gimmick-uses").filter((u) => u.진행순서_순서 === no);
  const allPhases = rowsOf(ws, "phases");
  const autoName = steps.map((c) => String(c.표시이름 ?? "")).filter(Boolean).join("·");   // 이름을 비워 두면 따라갈 이름

  return (
    <section className="editor" aria-label="페이즈 편집">
      <div className="row">
        <span className="row start">
          {/* 화살표는 페이즈를 옮기지 않고, 수정하는 페이즈를 이전/다음으로 바꾼다 */}
          <button type="button" className="small secondary" disabled={index === 0} aria-label="이전 페이즈 수정" onClick={() => onNavigate(-1)}>←</button>
          <h3>{pad(index + 1)} 페이즈 편집</h3>
          <button type="button" className="small secondary" disabled={index === total - 1} aria-label="다음 페이즈 수정" onClick={() => onNavigate(1)}>→</button>
        </span>
        <span className="row start">
          <button type="button" className="small secondary" aria-label={`페이즈 ${index + 1} 삭제`}
            onClick={async () => {
              if (await call("DELETE", `/phases/${no}`)) onClose();   // 확인창 없이 바로 지운다(놓인 카드는 내려가고 뒤의 페이즈가 한 칸 앞으로 온다)
            }}>
            삭제
          </button>
          <button type="button" className="small secondary" onClick={onClose}>닫기</button>
        </span>
      </div>
      <div className="row start">
        <label className="inline">
          페이즈 이름
          <input value={name} maxLength={100} placeholder={autoName || "플레이어에게 보이는 이름"} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="inline">
          진행 시간(분)
          <input type="number" min={0} max={1440} value={time} onChange={(e) => setTime(e.target.value)} />
        </label>
        <button type="button" className="small secondary"
          onClick={() => void call("PATCH", `phases/${no}`, { 이름: name.trim() || null, 진행시간: Number(time) })}>
          이름·시간 저장
        </button>
      </div>
      <p className="muted">
        이름을 비워 두면 붙은 진행단계 이름을 따라갑니다{autoName ? ` (지금은 "${autoName}")` : ""}. 직접 정하면 그 이름이 우선합니다.
      </p>
      <AttachedCards title="진행단계" empty="붙은 진행단계가 없습니다. 아래 진행카드를 이 페이즈에 끌어다 놓으세요." rows={steps}
        lib={ws.bundle.library.phases} libCol="진행단계_번호" resource="phase-steps" phaseNo={no} call={call} ws={ws} allPhases={allPhases} />
      {uses.length > 0 && (
        <AttachedCards title="기믹" empty="" rows={uses} lib={ws.bundle.library.gimmicks} libCol="기믹_번호" resource="gimmick-uses"
          phaseNo={no} call={call} ws={ws} allPhases={allPhases} />
      )}
    </section>
  );
}

/** 페이즈에 붙은 진행단계(또는 기믹) 목록. 각각 이 페이즈에서만 쓰는 세부 설정을 바로 고치고, 다른 페이즈로 복사하거나 뗀다. */
function AttachedCards({ title, empty, rows, lib, libCol, resource, phaseNo, call, ws, allPhases }: {
  title: string; empty: string; rows: Row[]; lib: Record<string, LibraryRef>; libCol: string; resource: string;
  phaseNo: number; call: Call; ws: Workspace; allPhases: Row[];
}) {
  const [copying, setCopying] = useState<number | null>(null);
  const isCard = resource === "phase-steps";
  const idCol = isCard ? "번호" : "순서";
  return (
    <div className="linked" role="group" aria-label={title}>
      <span className="linked-title">{title}</span>
      {rows.length === 0 && <span className="muted">{empty}</span>}
      <ul className="attached">
        {rows.map((r) => {
          const ref = lib[String(r[libCol])];
          const id = r[idCol] as number;
          // 같은 카드가 둘 이상이면 서버가 계산해 둔 "1차 ○○" 이름을 쓴다.
          const base = (isCard && typeof r.표시이름 === "string" ? r.표시이름 : ref?.이름) ?? title;
          return (
            <li key={String(id)} className={`attached-card${ref?.삭제됨 ? " deleted" : ""}`} role="group" aria-label={`${base} 수정`}>
              <div className="row">
                <span>
                  <strong>{base}</strong>{" "}
                  {ref ? <span className="muted">v{ref.버전}</span> : <span className="muted">#{String(r[libCol])}</span>}
                  {ref?.삭제됨 && <span className="muted"> · 삭제된 항목</span>}
                </span>
                <span className="row start">
                  <button type="button" className="small secondary" aria-label={`${base} 복사`} aria-expanded={copying === id}
                    onClick={() => setCopying(copying === id ? null : id)}>
                    복사
                  </button>
                  <button type="button" className="small secondary" aria-label={`${base} 떼기`} onClick={() => void call("DELETE", `${resource}/${id}`)}>
                    떼기
                  </button>
                </span>
              </div>
              <SettingsEditor key={`${id}:${JSON.stringify(r.설정 ?? null)}`} resource={resource} id={id} value={r.설정}
                showTab={isCard} call={call} />
              {copying === id && (
                <CopyEditor resource={resource} libCol={libCol} row={r} fromNo={phaseNo} allPhases={allPhases} ws={ws} call={call}
                  onDone={() => setCopying(null)} />
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** 놓은 카드·기믹을 세부 설정째로 다른 페이즈에 복사한다. 같은 진행단계는 한 페이즈에 한 번만 놓을 수 있어 이미 있는 페이즈는 뺀다. */
function CopyEditor({ resource, libCol, row, fromNo, allPhases, ws, call, onDone }: {
  resource: string; libCol: string; row: Row; fromNo: number; allPhases: Row[]; ws: Workspace; call: Call; onDone: () => void;
}) {
  const isCard = resource === "phase-steps";
  const taken = new Set(
    rowsOf(ws, resource).filter((r) => r[libCol] === row[libCol]).map((r) => r.진행순서_순서 as number),
  );
  const targets = allPhases.filter((p) => p.순서 !== fromNo && !(isCard && taken.has(p.순서 as number)));
  const [target, setTarget] = useState("");
  return (
    <div className="settings" role="group" aria-label="복사">
      {targets.length === 0 ? (
        <p className="muted">복사할 수 있는 다른 페이즈가 없습니다.{isCard ? " (같은 진행단계는 한 페이즈에 한 번만 놓을 수 있습니다)" : ""}</p>
      ) : (
        <label>
          복사할 페이즈
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">고르기…</option>
            {targets.map((p) => <option key={String(p.순서)} value={String(p.순서)}>{phaseLabel(ws, p.순서 as number)}</option>)}
          </select>
        </label>
      )}
      <div className="row start">
        <button type="button" className="small" disabled={!target}
          onClick={async () => {
            if (await call("POST", resource, { 진행순서_순서: Number(target), [libCol]: row[libCol], 설정: row.설정 ?? null })) onDone();
          }}>
          복사
        </button>
        <button type="button" className="small secondary" onClick={onDone}>닫기</button>
      </div>
    </div>
  );
}

const asObject = (v: unknown): Record<string, unknown> =>
  v !== null && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};

/**
 * 카드·기믹을 이 페이즈에 놓을 때만 적용하는 세부 설정. 비우면 정의의 기본값을 쓴다.
 * 카드에는 "다음 페이즈에도 탭 남기기"를 따로 보여 준다(기본: 남김). 나머지는 JSON 으로 직접 쓴다(내부 구조는 엔진 설계에서 정함).
 */
function SettingsEditor({ resource, id, value, showTab, call }: {
  resource: string; id: number; value: unknown; showTab: boolean; call: Call;
}) {
  const current = asObject(value);
  const { [KEEP_TAB]: keepRaw, ...rest } = current;
  const [keepTab, setKeepTab] = useState(keepRaw !== false);
  const [text, setText] = useState(Object.keys(rest).length ? JSON.stringify(rest, null, 2) : "");
  const [error, setError] = useState<string | null>(null);

  async function save() {
    let extra: Record<string, unknown> = {};
    if (text.trim() !== "") {
      try {
        const parsed: unknown = JSON.parse(text);
        if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
        extra = parsed as Record<string, unknown>;
      } catch {
        setError("JSON 객체({...})로 써 주세요");
        return;
      }
    }
    const next = showTab && !keepTab ? { ...extra, [KEEP_TAB]: false } : extra;
    setError(null);
    await call("PATCH", `${resource}/${id}`, { 설정: Object.keys(next).length ? next : null });
  }

  return (
    <div className="settings" role="group" aria-label="세부 설정">
      {showTab && (
        <label className="check">
          <input type="checkbox" checked={keepTab} onChange={(e) => setKeepTab(e.target.checked)} />
          이 카드가 만든 탭을 다음 페이즈에도 남기기
        </label>
      )}
      <label>
        그 밖의 세부 설정 (JSON)
        <textarea rows={4} value={text} placeholder="비우면 정의의 기본값을 씁니다" onChange={(e) => setText(e.target.value)} />
      </label>
      {error && <p role="alert" className="error">{error}</p>}
      <div className="row start">
        <button type="button" className="small" onClick={() => void save()}>설정 저장</button>
      </div>
    </div>
  );
}
