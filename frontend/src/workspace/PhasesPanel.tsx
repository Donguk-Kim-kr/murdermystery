import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { errorMessage, http } from "../api/client";
import type { Hit } from "./flowDrag";
import { useFlowDrag, type Payload } from "./useFlowDrag";
import { rowsOf, useWorkspace, type LibraryRef, type Row, type SettingDef, type Workspace } from "./workspace";

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
const KEEP_TAB = "내용유지";
const STORY_PICKS = "개인서사공개";
const CANDIDATES = "후보";
const QUESTIONS = "질문";

/** 스크립트가 설정정의로 정한 입력칸 중 이 화면이 직접 그리는 것들(서사·후보·질문은 따로 전용 입력이 있다). */
const GENERIC_KINDS = ["숫자", "선택", "켜짐", "글", "여러선택"];

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
  /** 여러 개를 한꺼번에 선택하거나(on) 해제한다. */
  const setMany = (kind: "steps" | "gimmicks", ids: number[], on: boolean) =>
    update({ ...tray, [kind]: on ? [...tray[kind], ...ids.filter((x) => !tray[kind].includes(x))] : tray[kind].filter((x) => !ids.includes(x)) });
  return { tray, toggle, setMany };
}

function PhasesBody({ workId, ws, phaseItems, gimmickItems }: {
  workId: number; ws: Workspace; phaseItems: LibraryItem[]; gimmickItems: LibraryItem[];
}) {
  const serverPhases = rowsOf(ws, "phases");
  // 페이즈 카드를 놓은 뒤 서버가 응답할 때까지는 놓은 자리에 그대로 보여 준다(원래 자리로 돌아갔다가 다시 옮겨 가 보이지 않게).
  // base 는 놓을 때의 서버 목록이고, 다시 읽어 와 목록이 바뀌면 더는 적용하지 않는다.
  const [settling, setSettling] = useState<{ base: Row[]; from: number; to: number } | null>(null);
  const phases = settling && settling.base === serverPhases ? moved(serverPhases, settling.from, settling.to) : serverPhases;
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);   // 수정 패널에 열린 페이즈의 칸 번호
  const [vertical, setVertical] = useState(false);
  const [loader, setLoader] = useState(false);
  const flowRef = useRef<HTMLOListElement>(null);
  const { tray, toggle, setMany } = useTray(workId);
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
    try {
      await drop(p, hit);
    } finally {
      setSettling(null);
    }
  }

  async function drop(p: Payload, hit: Hit) {
    if (!hit) return;
    setError(null);
    if (hit.type === "attach") {
      await putInto(hit.order, p);
    } else if (p.kind === "phase") {
      // hit.index 는 끌고 있는 카드를 뺀 목록에서의 자리이다 → 옮길 위치(1부터)는 index + 1
      if (hit.index !== p.index) {
        setSettling({ base: serverPhases, from: p.index, to: hit.index });
        await req("POST", `/phases/${p.order}/move`, { position: hit.index + 1 });
      }
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
      <ol className={`flow${settling ? " settling" : ""}`} ref={flowRef} aria-label="게임 흐름">
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
      {loader && <CardLoader phaseItems={phaseItems} gimmickItems={gimmickItems} tray={tray} onToggle={toggle} onSetMany={setMany} onClose={() => setLoader(false)} />}
    </section>
  );
}

/** 목록에서 from 번째를 빼 to 번째(빼고 난 목록에서의 자리)에 끼운 새 목록. */
function moved<T>(list: T[], from: number, to: number): T[] {
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
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
function CardLoader({ phaseItems, gimmickItems, tray, onToggle, onSetMany, onClose }: {
  phaseItems: LibraryItem[]; gimmickItems: LibraryItem[]; tray: { steps: number[]; gimmicks: number[] };
  onToggle: (kind: "steps" | "gimmicks", id: number) => void;
  onSetMany: (kind: "steps" | "gimmicks", ids: number[], on: boolean) => void; onClose: () => void;
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
  // 전체 선택은 보이는 것 중 이름마다 가장 높은 버전만 고른다(옛 버전까지 한꺼번에 놓이지 않게). 검색 중이면 보이는 것들만 본다.
  const newest = shown.filter((i) => !shown.some((x) => x.이름 === i.이름 && x.버전 > i.버전));
  const allLoaded = newest.length > 0 && newest.every((i) => tray[kind].includes(i.번호));
  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label="진행카드 불러오기" onClick={(e) => { e.stopPropagation(); setTipOpen(null); }}>
        <h2>진행카드 불러오기</h2>
        <div className="row start" role="tablist" aria-label="종류">
          <button type="button" role="tab" aria-selected={kind === "steps"} className={`tab${kind === "steps" ? " active" : ""}`}
            onClick={() => setKind("steps")}>진행단계</button>
          <button type="button" role="tab" aria-selected={kind === "gimmicks"} className={`tab${kind === "gimmicks" ? " active" : ""}`}
            onClick={() => setKind("gimmicks")}>기믹</button>
          <button type="button" className="small secondary push-right" disabled={newest.length === 0}
            onClick={() => onSetMany(kind, newest.map((i) => i.번호), !allLoaded)}>
            {allLoaded ? "전체 해제" : "전체 선택"}
          </button>
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
        <div className="dialog-footer">
          <button type="button" onClick={onClose}>확인</button>
        </div>
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

/** 고른 페이즈의 수정 패널: 이름·시간, 이전/다음 페이즈로 넘어가기, 삭제, 붙은 진행단계·기믹 목록(골라서 수정·삭제). */
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
  const autoName = steps.map((c) => String(c.표시이름 ?? "")).filter(Boolean).join("·");   // 이름을 비워 두면 따라갈 이름

  return (
    <section className="editor" aria-label="페이즈 편집">
      <div className="row">
        <span className="row start">
          {/* 화살표는 페이즈를 옮기지 않고, 수정하는 페이즈를 이전/다음으로 바꾼다 */}
          <button type="button" className="small secondary" disabled={index === 0} aria-label="이전 페이즈 수정" onClick={() => onNavigate(-1)}>←</button>
          <h3>{pad(index + 1)}</h3>
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
      <AttachedCards key={`step:${no}`} title="진행단계" empty="붙은 진행단계가 없습니다. 아래 진행카드를 이 페이즈에 끌어다 놓으세요." rows={steps}
        lib={ws.bundle.library.phases} libCol="진행단계_번호" resource="phase-steps" call={call}
        characters={(ws.bundle.characters as Row[] | undefined) ?? []} storyParts={ws.bundle.story?.공통스토리_부분수 ?? 1} />
      {uses.length > 0 && (
        <AttachedCards key={`gimmick:${no}`} title="기믹" empty="" rows={uses} lib={ws.bundle.library.gimmicks} libCol="기믹_번호" resource="gimmick-uses"
          call={call} />
      )}
    </section>
  );
}

/** 페이즈에 붙은 진행단계(또는 기믹) 목록. 하나를 골라야 그 카드의 수정 항목과 삭제 버튼이 나타난다(다시 누르면 접힌다). */
function AttachedCards({ title, empty, rows, lib, libCol, resource, call, characters = [], storyParts = 1 }: {
  title: string; empty: string; rows: Row[]; lib: Record<string, LibraryRef>; libCol: string; resource: string; call: Call;
  characters?: Row[]; storyParts?: number;
}) {
  const [selected, setSelected] = useState<number | null>(null);
  const isCard = resource === "phase-steps";
  const idCol = isCard ? "번호" : "순서";
  // 같은 카드가 둘 이상이면 서버가 계산해 둔 "1차 ○○" 이름을 쓴다.
  const nameOf = (r: Row) => (isCard && typeof r.표시이름 === "string" ? r.표시이름 : lib[String(r[libCol])]?.이름) ?? title;
  const current = rows.find((r) => r[idCol] === selected);
  const ref = current ? lib[String(current[libCol])] : undefined;
  return (
    <div className="linked" role="group" aria-label={title}>
      <span className="linked-title">{title}</span>
      {rows.length === 0 && <span className="muted">{empty}</span>}
      <ul className="attached-list">
        {rows.map((r) => {
          const id = r[idCol] as number;
          const on = id === selected;
          return (
            <li key={String(id)}>
              <button type="button" className={`attached-pick${on ? " on" : ""}`} aria-pressed={on}
                onClick={() => setSelected(on ? null : id)}>
                {nameOf(r)}
              </button>
            </li>
          );
        })}
      </ul>
      {current && (
        <div className={`attached-card${ref?.삭제됨 ? " deleted" : ""}`} role="group" aria-label={`${nameOf(current)} 수정`}>
          <div className="row">
            <span>
              <strong>{nameOf(current)}</strong>{" "}
              {ref ? <span className="muted">v{ref.버전}</span> : <span className="muted">#{String(current[libCol])}</span>}
              {ref?.삭제됨 && <span className="muted"> · 삭제된 항목</span>}
            </span>
            <button type="button" className="small secondary" aria-label={`${nameOf(current)} 삭제`}
              onClick={async () => {
                if (await call("DELETE", `${resource}/${current[idCol] as number}`)) setSelected(null);
              }}>
              삭제
            </button>
          </div>
          <SettingsEditor key={`${selected}:${JSON.stringify(current.설정 ?? null)}`} resource={resource} id={current[idCol] as number}
            value={current.설정} showTab={isCard} call={call} characters={characters} settingKeys={ref?.사용설정 ?? []} defs={ref?.설정정의 ?? []} declared={ref?.설정정의 != null}
            storyParts={storyParts} />
        </div>
      )}
    </div>
  );
}

const asObject = (v: unknown): Record<string, unknown> =>
  v !== null && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};

/**
 * 카드·기믹을 이 페이즈에 놓을 때만 적용하는 세부 설정. 비우면 정의의 기본값을 쓴다.
 * 카드에는 "내용 유지"(이 페이즈가 끝나도 내용을 남겨 계속 볼 수 있게 함)를 따로 보여 준다(기본: 남김). 상세 설명 글은 아직 두지 않는다. 나머지는 JSON 으로 직접 쓴다(내부 구조는 엔진 설계에서 정함).
 */
function SettingsEditor({ resource, id, value, showTab, call, characters, settingKeys, defs, declared, storyParts }: {
  resource: string; id: number; value: unknown; showTab: boolean; call: Call; characters: Row[]; settingKeys: string[]; defs: SettingDef[]; declared: boolean; storyParts: number;
}) {
  const current = asObject(value);
  const showPicks = settingKeys.includes(STORY_PICKS);
  const showCandidates = settingKeys.includes(CANDIDATES);
  const showQuestions = settingKeys.includes(QUESTIONS);
  const { [KEEP_TAB]: keepRaw, [STORY_PICKS]: picksRaw, [CANDIDATES]: candidatesRaw, [QUESTIONS]: questionsRaw, ...restAll } = current;
  const simpleShown = defs.filter((d) => GENERIC_KINDS.includes(d.종류));
  const commonDef = defs.find((d) => d.종류 === "공통서사");               // 공통 스토리 카드: 보여 줄 부분 번호
  // 전용 입력으로 다루는 설정만 JSON 칸에서 뺀다(스크립트가 쓰지 않는 카드에서는 값을 그대로 둔다).
  const rest: Record<string, unknown> = { ...restAll };
  for (const d of simpleShown) delete rest[d.키];
  if (commonDef) delete rest[commonDef.키];
  const [commonPicked, setCommonPicked] = useState<number[]>(() => {
    const raw = commonDef ? current[commonDef.키] : undefined;
    return Array.isArray(raw) ? raw.filter((n): n is number => Number.isInteger(n) && n >= 1) : [1];
  });
  const [simple, setSimple] = useState<Record<string, unknown>>(() =>
    Object.fromEntries(simpleShown.map((d) => [d.키, current[d.키] ?? d.기본 ?? (d.종류 === "글" ? "" : null)])));
  if (!showPicks && picksRaw !== undefined) rest[STORY_PICKS] = picksRaw;
  if (!showCandidates && candidatesRaw !== undefined) rest[CANDIDATES] = candidatesRaw;
  if (!showQuestions && questionsRaw !== undefined) rest[QUESTIONS] = questionsRaw;
  const [questions, setQuestions] = useState<Record<string, QuestionDraft>>(() => readQuestions(questionsRaw));
  const allPlayable = characters.filter((c) => c.NPC !== true).map((c) => Number(c.순서));
  const [candidates, setCandidates] = useState<number[]>(
    Array.isArray(candidatesRaw) ? candidatesRaw.filter((n): n is number => Number.isInteger(n)) : allPlayable,
  );
  // 인물이 아닌 후보(사고사, 자살 …)
  const [extras, setExtras] = useState<string[]>(
    Array.isArray(candidatesRaw) ? candidatesRaw.filter((v): v is string => typeof v === "string") : [],
  );
  const [keepTab, setKeepTab] = useState(keepRaw !== false);
  const [text, setText] = useState(Object.keys(rest).length ? JSON.stringify(rest, null, 2) : "");
  const [picked, setPicked] = useState<Record<string, number[]>>(() => storyPicks(picksRaw));
  const [error, setError] = useState<string | null>(null);

  async function save() {
    let extra: Record<string, unknown> = declared ? { ...rest } : {};     // 스크립트가 설정 칸을 정한 카드는 JSON 을 보이지 않는다(칸에 없는 기존 값은 그대로 둔다)
    if (!declared && text.trim() !== "") {
      try {
        const parsed: unknown = JSON.parse(text);
        if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
        extra = parsed as Record<string, unknown>;
      } catch {
        setError("JSON 객체({...})로 써 주세요");
        return;
      }
    }
    // 기본(서사 전체)과 같은 선택은 따로 저장하지 않는다.
    const totals = Object.fromEntries(characters.map((c) => [String(c.순서), Math.max(Number(c.서사_부분수 ?? 0), 1)]));
    const changed = Object.fromEntries(
      Object.entries(picked).filter(([key, nums]) => !(nums.length === (totals[key] ?? 1) && nums.every((n, i) => n === i + 1))),
    );
    let next: Record<string, unknown> = showPicks && Object.keys(changed).length ? { ...extra, [STORY_PICKS]: changed } : extra;
    // 기본(플레이어가 맡는 인물 모두)과 같은 선택은 따로 저장하지 않는다.
    const isDefault = extras.length === 0 && candidates.length === allPlayable.length && allPlayable.every((n) => candidates.includes(n));
    const asked = writeQuestions(questions);
    if (showQuestions && Object.keys(asked).length) next = { ...next, [QUESTIONS]: asked };
    if (showCandidates && !isDefault) next = { ...next, [CANDIDATES]: [...[...candidates].sort((a, b) => a - b), ...extras] };
    if (showTab && !keepTab) next = { ...next, [KEEP_TAB]: false };
    if (commonDef) {
      const list = [...commonPicked].sort((a, b) => a - b);
      if (list.length === 0) {
        setError("보여 줄 공통 스토리 부분을 하나 이상 골라 주세요");
        return;
      }
      if (JSON.stringify(list) !== JSON.stringify([1])) next = { ...next, [commonDef.키]: list };
    }
    for (const d of simpleShown) {
      const v = simple[d.키];
      if (d.종류 === "글") {
        if (typeof v === "string" && v.trim() !== "" && v.trim() !== String(d.기본 ?? "")) next = { ...next, [d.키]: v.trim() };
      } else if (d.종류 === "숫자") {
        const n = Number(v);
        if (!Number.isInteger(n) || n < (d.최소 ?? 0)) {
          setError(`${d.이름}: ${d.최소 ?? 0} 이상의 정수로 입력해 주세요`);
          return;
        }
        if (n !== d.기본) next = { ...next, [d.키]: n };
      } else if (d.종류 === "여러선택") {
        const allowed = (d.선택 ?? []).map(([val]) => val);
        const list = (v as unknown[]).filter((o) => allowed.includes(o as string));
        if (list.length === 0) {
          setError(`${d.이름}: 하나 이상 골라 주세요`);
          return;
        }
        if (JSON.stringify(list) !== JSON.stringify(d.기본)) next = { ...next, [d.키]: list };
      } else if (v !== d.기본) next = { ...next, [d.키]: v };
    }
    setError(null);
    await call("PATCH", `${resource}/${id}`, { 설정: Object.keys(next).length ? next : null });
  }

  return (
    <div className="settings" role="group" aria-label="세부 설정">
      {showTab && (
        <label className="check">
          <input type="checkbox" checked={keepTab} onChange={(e) => setKeepTab(e.target.checked)} />
          내용 유지
        </label>
      )}
      {commonDef && (
        <fieldset className="story-picks">
          <legend>{commonDef.이름}</legend>
          <div className="row start">
            {Array.from({ length: Math.max(storyParts, ...commonPicked, 1) }, (_, i) => i + 1).map((n) => (
              <label key={n} className="check">
                <input type="checkbox" checked={commonPicked.includes(n)}
                  onChange={(e) => setCommonPicked(e.target.checked ? [...commonPicked, n] : commonPicked.filter((x) => x !== n))} />
                {`${n}부분`}
              </label>
            ))}
          </div>
          {storyParts > commonPicked.length && <span className="hint">작품의 공통 스토리는 {storyParts}부분입니다. 고르지 않은 부분은 이 카드에서 보이지 않습니다</span>}
        </fieldset>
      )}
      {simpleShown.map((d) => (
        <SimpleSettingInput key={d.키} d={d} value={simple[d.키]} onChange={(v) => setSimple({ ...simple, [d.키]: v })} />
      ))}
      {showPicks && <StoryPicks characters={characters} picked={picked} onChange={setPicked} />}
      {showQuestions && <QuestionPicks characters={characters} value={questions} onChange={setQuestions} />}
      {showCandidates && (
        <CandidatePicks characters={characters} selected={candidates} onChange={setCandidates} extras={extras} onExtras={setExtras} />
      )}
      {!declared && (
        <label>
          그 밖의 세부 설정 (JSON)
          <textarea rows={4} value={text} placeholder="비우면 정의의 기본값을 씁니다" onChange={(e) => setText(e.target.value)} />
        </label>
      )}
      {error && <p role="alert" className="error">{error}</p>}
      <div className="row start">
        <button type="button" className="small" onClick={() => void save()}>설정 저장</button>
      </div>
    </div>
  );
}

function SimpleSettingInput({ d, value, onChange }: { d: SettingDef; value: unknown; onChange: (v: unknown) => void }) {
  const hint = d.설명 ? <span className="hint">{d.설명}</span> : null;
  const options = d.선택 ?? [];
  if (d.종류 === "켜짐")
    return (
      <div className="field">
        <label className="check">
          <input type="checkbox" checked={value === true} onChange={(e) => onChange(e.target.checked)} />
          {d.이름}
        </label>
        {hint}
      </div>
    );
  if (d.종류 === "여러선택") {
    const chosen = (value as unknown[]) ?? [];
    return (
      <fieldset className="story-picks">
        <legend>{d.이름}</legend>
        <div className="row start">
          {options.map(([val, label]) => (
            <label key={String(val)} className="check">
              <input type="checkbox" checked={chosen.includes(val)}
                onChange={(e) => onChange(options.map(([v]) => v).filter((x) => (x === val ? e.target.checked : chosen.includes(x))))} />
              {label}
            </label>
          ))}
        </div>
        {hint}
      </fieldset>
    );
  }
  return (
    <div className="field">
      <label>
        {d.이름}
        {d.종류 === "선택" ? (
          <select value={String(value)} onChange={(e) => onChange(options.find(([v]) => String(v) === e.target.value)?.[0] ?? e.target.value)}>
            {options.map(([v, t]) => <option key={String(v)} value={String(v)}>{t}</option>)}
          </select>
        ) : d.종류 === "숫자" ? (
          <input type="number" min={d.최소 ?? 0} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />
        ) : (
          <input value={String(value ?? "")} maxLength={500} onChange={(e) => onChange(e.target.value)} />
        )}
      </label>
      {hint}
    </div>
  );
}

/** 저장된 `개인서사공개`({"인물 순서": [서사 번호, …]})를 읽는다. 모양이 다른 값은 건너뛴다. */
function storyPicks(raw: unknown): Record<string, number[]> {
  const out: Record<string, number[]> = {};
  for (const [key, nums] of Object.entries(asObject(raw))) {
    if (Array.isArray(nums)) out[key] = nums.filter((n): n is number => Number.isInteger(n) && n >= 1).sort((a, b) => a - b);
  }
  return out;
}

interface QuestionDraft {
  text: string;
  /** 선택지. 비우면 자유롭게 글로 답한다 */
  choices: string[];
}

/** 저장된 `질문`({"인물 순서": "질문" 또는 {질문, 선택}})을 입력용 값으로 읽는다. 모양이 다른 값은 건너뛴다. */
function readQuestions(raw: unknown): Record<string, QuestionDraft> {
  const out: Record<string, QuestionDraft> = {};
  for (const [key, def] of Object.entries(asObject(raw))) {
    if (typeof def === "string") out[key] = { text: def, choices: [] };
    else {
      const d = asObject(def);
      if (typeof d.질문 === "string")
        out[key] = { text: d.질문, choices: Array.isArray(d.선택) ? d.선택.filter((c): c is string => typeof c === "string") : [] };
    }
  }
  return out;
}

/** 입력한 질문을 저장 모양으로 바꾼다. 질문이 비어 있는 인물은 뺀다(질문이 없는 인물은 답할 것이 없다). */
function writeQuestions(drafts: Record<string, QuestionDraft>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, d] of Object.entries(drafts)) {
    const text = d.text.trim();
    if (!text) continue;
    out[key] = d.choices.length ? { 질문: text, 선택: d.choices } : text;
  }
  return out;
}

/** 개인 질문 카드: 인물마다 다른 질문을 정한다. 선택지를 하나씩 추가하면 고르는 질문이고, 없으면 글로 답하는 질문이다. 질문을 비운 인물은 답할 것이 없다. */
function QuestionPicks({ characters, value, onChange }: {
  characters: Row[]; value: Record<string, QuestionDraft>; onChange: (next: Record<string, QuestionDraft>) => void;
}) {
  const players = characters.filter((c) => c.NPC !== true);
  return (
    <fieldset className="story-picks">
      <legend>개인 질문</legend>
      <p className="muted">
        인물마다 다른 질문을 정합니다. 선택지를 만들면 플레이어가 그중에서 고르고, 만들지 않으면 글로 답합니다(엔딩 조건에서 가르기 쉬운 것은 선택지입니다).
        질문을 비워 두면 그 인물은 답할 것이 없습니다. 답은 게임 변수 "이름:인물 순서"에 남아 엔딩 조건이 읽습니다.
      </p>
      {players.map((c) => (
        <QuestionRow key={String(c.순서)} name={String(c.이름)} draft={value[String(c.순서)] ?? { text: "", choices: [] }}
          onChange={(draft) => onChange({ ...value, [String(c.순서)]: draft })} />
      ))}
    </fieldset>
  );
}

function QuestionRow({ name, draft, onChange }: { name: string; draft: QuestionDraft; onChange: (next: QuestionDraft) => void }) {
  const [newChoice, setNewChoice] = useState("");
  const add = () => {
    const text = newChoice.trim();
    if (text && text.length <= 50 && !draft.choices.includes(text) && draft.choices.length < 30) onChange({ ...draft, choices: [...draft.choices, text] });
    setNewChoice("");
  };
  return (
    <div className="question-pick" role="group" aria-label={`${name}의 질문`}>
      <strong>{name}</strong>
      <input aria-label={`${name} 질문`} value={draft.text} maxLength={300} placeholder="질문" onChange={(e) => onChange({ ...draft, text: e.target.value })} />
      <div className="story-pick">
        {draft.choices.map((choice) => (
          <span key={choice} className="chip">
            {choice}
            <button type="button" className="small secondary" aria-label={`${name} 선택지 ${choice} 삭제`}
              onClick={() => onChange({ ...draft, choices: draft.choices.filter((c) => c !== choice) })}>
              ×
            </button>
          </span>
        ))}
        {draft.choices.length === 0 && <span className="muted">선택지 없음(글로 답함)</span>}
      </div>
      <div className="row start">
        <input
          aria-label={`${name} 새 선택지`}
          value={newChoice}
          maxLength={50}
          placeholder="선택지 추가 (예: 예)"
          onChange={(e) => setNewChoice(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <button type="button" className="small secondary" aria-label={`${name} 선택지 추가`} onClick={add}>추가</button>
      </div>
    </div>
  );
}

/** 투표 카드: 투표할 수 있는 후보를 고른다. 인물(NPC 포함)과 인물이 아닌 선택지(사고사, 자살 …)를 둘 수 있다. 기본은 플레이어가 맡는 인물 모두이다. */
function CandidatePicks({ characters, selected, onChange, extras, onExtras }: {
  characters: Row[]; selected: number[]; onChange: (next: number[]) => void; extras: string[]; onExtras: (next: string[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const text = draft.trim();
    if (text && !extras.includes(text) && text.length <= 50) onExtras([...extras, text]);
    setDraft("");
  };
  return (
    <fieldset className="story-picks">
      <legend>투표 후보</legend>
      <p className="muted">투표에서 고를 수 있는 후보입니다. 자기 인물에게는 투표할 수 없습니다.</p>
      <div className="story-pick">
        {characters.map((c) => {
          const slot = Number(c.순서);
          return (
            <label key={slot} className="check">
              <input
                type="checkbox"
                checked={selected.includes(slot)}
                onChange={(e) => onChange(e.target.checked ? [...selected, slot] : selected.filter((n) => n !== slot))}
              />
              {String(c.이름)}
              {c.NPC === true ? " (NPC)" : ""}
            </label>
          );
        })}
      </div>
      <div className="story-pick">
        {extras.map((text) => (
          <span key={text} className="chip">
            {text}
            <button type="button" className="small secondary" aria-label={`${text} 후보 삭제`} onClick={() => onExtras(extras.filter((t) => t !== text))}>
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="row start">
        <input
          aria-label="인물이 아닌 후보"
          value={draft}
          maxLength={50}
          placeholder="예: 사고사"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <button type="button" className="small secondary" onClick={add}>후보 추가</button>
      </div>
    </fieldset>
  );
}

/** 프로필 숙지 카드: 인물마다 이 카드가 보여 줄 서사를 고른다(여러 개 가능, 기본은 서사 1). */
function StoryPicks({ characters, picked, onChange }: {
  characters: Row[]; picked: Record<string, number[]>; onChange: (next: Record<string, number[]>) => void;
}) {
  const players = characters.filter((c) => c.NPC !== true);
  return (
    <fieldset className="story-picks">
      <legend>개인 서사 공개</legend>
      <p className="muted">이 카드가 인물마다 보여 줄 서사를 고릅니다. 따로 고르지 않으면 서사 전체를 보여 줍니다.</p>
      {players.length === 0 && <p className="muted">플레이할 수 있는 인물이 없습니다.</p>}
      {players.map((c) => {
        const key = String(c.순서);
        const total = Number(c.서사_부분수 ?? 0);
        const slots = Array.from({ length: Math.max(total, 1) }, (_, i) => i + 1);
        const chosen = picked[key] ?? slots;                     // 기본은 서사 전체
        const missing = chosen.filter((n) => n > total);
        return (
          <div key={key} className="story-pick" role="group" aria-label={`${String(c.이름)}의 개인 서사 공개`}>
            <strong>{String(c.이름)}</strong>
            {total === 0 ? (
              <span className="muted">서사가 없습니다</span>
            ) : (
              slots.map((n) => (
                <label key={n} className="check">
                  <input
                    type="checkbox"
                    checked={chosen.includes(n)}
                    onChange={(e) =>
                      onChange({ ...picked, [key]: (e.target.checked ? [...chosen, n] : chosen.filter((m) => m !== n)).sort((a, b) => a - b) })
                    }
                  />
                  서사 {n}
                </label>
              ))
            )}
            {missing.length > 0 && total > 0 && (
              <span role="status" className="error">
                {missing.map((n) => `서사 ${n}`).join(", ")}은(는) 없습니다(서사 {total}개)
              </span>
            )}
          </div>
        );
      })}
    </fieldset>
  );
}
