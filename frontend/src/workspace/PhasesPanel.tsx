import { useEffect, useState, type DragEvent, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { errorMessage, http } from "../api/client";
import { rowsOf, useWorkspace, type LibraryRef, type Row, type Workspace } from "./workspace";

export interface LibraryItem {
  번호: number;
  이름: string;
  버전: number;
  설명: string | null;
  변경내역: string | null;
  공통: boolean;
}

const itemLabel = (i: LibraryItem) => `${i.이름} v${i.버전}${i.변경내역 ? ` — ${i.변경내역}` : ""}${i.공통 ? " (공통)" : ""}`;

type Call = (method: string, path: string, body?: unknown) => Promise<boolean>;

/** 칸에 놓은 카드·기믹의 세부 설정(`설정`)에서 다음 페이즈에도 탭을 남길지를 가리키는 키. 이름은 임시이며 엔진 설계에서 확정한다. */
const KEEP_TAB = "탭유지";

/** 끌고 있는 것. 브라우저는 끄는 동안 데이터를 읽지 못하게 하므로 화면 상태로 들고 있다. */
type Drag =
  | { kind: "library-step"; id: number }
  | { kind: "library-gimmick"; id: number }
  | { kind: "chip-step"; id: number }      // 진행구성 번호
  | { kind: "chip-gimmick"; id: number }   // 기믹적용 순서
  | { kind: "phase"; order: number };
type DragApi = {
  drag: Drag | null; over: string | null;
  start: (e: DragEvent, d: Drag) => void; end: () => void;
  target: (id: string, accepts: (d: Drag) => boolean, onDrop: (d: Drag) => void) => {
    onDragOver: (e: DragEvent) => void; onDragLeave: () => void; onDrop: (e: DragEvent) => void;
  };
};

/**
 * 게임 흐름 화면: 페이즈(칸)를 왼쪽에서 오른쪽으로 늘어놓고, 칸마다 진행단계 카드와 기믹을 붙인다.
 * 카드 상자의 카드를 끌어 페이즈 위에 놓으면 붙고, 페이즈 사이 틈에 놓으면 새 페이즈로 끼워 넣어 뒤가 밀린다.
 * 페이즈와 붙은 카드도 끌어서 옮긴다(서버가 칸의 내용을 옮기므로 붙여 둔 카드·기믹·투표가 따라간다).
 * 끌기가 어려운 경우를 위해 버튼과 고르기 칸도 그대로 둔다.
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

function PhasesBody({ workId, ws, phaseItems, gimmickItems }: {
  workId: number; ws: Workspace; phaseItems: LibraryItem[]; gimmickItems: LibraryItem[];
}) {
  const phases = rowsOf(ws, "phases");
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [over, setOver] = useState<string | null>(null);

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

  const dnd: DragApi = {
    drag, over,
    start(e, d) {
      e.stopPropagation();
      e.dataTransfer?.setData("text/plain", "murdermystery"); // 일부 브라우저는 데이터가 있어야 끌기가 시작된다
      if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
      setDrag(d);
    },
    end() { setDrag(null); setOver(null); },
    target(id, accepts, onDrop) {
      return {
        onDragOver(e) {
          if (!drag || !accepts(drag)) return;
          e.preventDefault(); // 놓을 수 있다는 표시
          if (over !== id) setOver(id);
        },
        onDragLeave() { if (over === id) setOver(null); },
        onDrop(e) {
          if (!drag || !accepts(drag)) return;
          e.preventDefault();
          e.stopPropagation();
          const d = drag;
          setDrag(null);
          setOver(null);
          setError(null);
          onDrop(d);
        },
      };
    },
  };

  /** 놓은 것을 칸 slot 에 붙이거나 옮긴다. 성공 여부를 돌려준다(다시 읽기는 부르는 쪽). */
  async function putInto(slot: number, d: Drag): Promise<boolean> {
    switch (d.kind) {
      case "library-step":
        return !!(await req("POST", "phase-steps", { 진행순서_순서: slot, 진행단계_번호: d.id }));
      case "library-gimmick":
        return !!(await req("POST", "gimmick-uses", { 진행순서_순서: slot, 기믹_번호: d.id }));
      case "chip-step":
        return !!(await req("PATCH", `phase-steps/${d.id}`, { 진행순서_순서: slot }));
      case "chip-gimmick":
        return !!(await req("PATCH", `gimmick-uses/${d.id}`, { 진행순서_순서: slot }));
      default:
        return false;
    }
  }

  async function dropOnPhase(index: number, d: Drag) {
    if (d.kind === "phase") {
      const from = phases.findIndex((p) => p.순서 === d.order);
      if (from !== index) await req("POST", `/phases/${d.order}/move`, { position: index + 1 });
    } else {
      await putInto(phases[index].순서 as number, d);
    }
    await ws.reload();
  }

  /** 페이즈 사이 틈(0 은 맨 앞, 페이즈 수는 맨 끝)에 놓은 것. 카드·기믹이면 새 페이즈를 끼워 넣고 거기에 붙인다. */
  async function dropOnGap(gap: number, d: Drag) {
    if (d.kind === "phase") {
      const from = phases.findIndex((p) => p.순서 === d.order);
      const position = from < gap ? gap : gap + 1; // 자기 자신이 빠지면 뒤쪽 위치가 하나 당겨진다
      if (from !== position - 1) await req("POST", `/phases/${d.order}/move`, { position });
    } else {
      const made = await req<{ phases: Row[] }>("POST", "/phases/insert", { position: gap + 1, 이름: null, 진행시간: 30 });
      if (made) await putInto(made.data.phases[gap].순서 as number, d);
    }
    await ws.reload();
  }

  const empty = phases.length === 0;
  return (
    <section className="card" aria-label="페이즈">
      <h2>게임 흐름 <span className="muted">(페이즈 {phases.length}개)</span></h2>
      <p className="muted">
        왼쪽에서 오른쪽으로 게임이 진행됩니다. 아래 카드 상자의 카드를 끌어 페이즈 위에 놓으면 붙고,
        페이즈 사이 틈에 놓으면 새 페이즈로 끼워 넣어집니다. 페이즈와 붙은 카드도 끌어서 옮길 수 있습니다.
        카드와 기믹은 <Link to="/library">라이브러리</Link>에서 만듭니다.
      </p>
      <Palette phaseItems={phaseItems} gimmickItems={gimmickItems} dnd={dnd} />
      {empty && <p className="muted">아직 페이즈가 없습니다. 카드를 아래 칸에 놓거나 "페이즈 추가"로 시작하세요.</p>}
      <ol className="flow" aria-label="게임 흐름">
        {phases.map((p, i) => (
          <PhaseSlot key={String(p.순서)} gap={i} dnd={dnd} onGapDrop={dropOnGap}>
            <PhaseCard ws={ws} phase={p} index={i} total={phases.length}
              phaseItems={phaseItems} gimmickItems={gimmickItems} call={call}
              dnd={dnd} onDrop={(d) => void dropOnPhase(i, d)} />
          </PhaseSlot>
        ))}
        <li className="flow-end">
          <Gap index={phases.length} dnd={dnd} onGapDrop={dropOnGap} wide={empty} />
        </li>
      </ol>
      <InsertForm count={phases.length} call={call} />
      {error && <p role="alert" className="error">{error}</p>}
    </section>
  );
}

/** 카드 상자: 라이브러리의 진행단계·기믹. 끌어서 페이즈에 붙인다. */
function Palette({ phaseItems, gimmickItems, dnd }: { phaseItems: LibraryItem[]; gimmickItems: LibraryItem[]; dnd: DragApi }) {
  const group = (title: string, items: LibraryItem[], kind: "library-step" | "library-gimmick", empty: string) => (
    <div className="palette-group" role="group" aria-label={`카드 상자 ${title}`}>
      <span className="linked-title">{title}</span>
      {items.length === 0 && <span className="muted">{empty}</span>}
      <ul className="chips">
        {items.map((i) => (
          <li key={i.번호} className="chip accent draggable" draggable title="끌어서 페이즈에 놓기"
            onDragStart={(e) => dnd.start(e, { kind, id: i.번호 })} onDragEnd={dnd.end}>
            {itemLabel(i)}
          </li>
        ))}
      </ul>
    </div>
  );
  return (
    <div className="palette" aria-label="카드 상자">
      {group("진행단계 카드", phaseItems, "library-step", "라이브러리에서 진행단계를 먼저 만들어 주세요.")}
      {group("기믹 카드", gimmickItems, "library-gimmick", "만들어 둔 기믹이 없습니다.")}
    </div>
  );
}

/** 페이즈 앞의 틈 + 페이즈 칸. */
function PhaseSlot({ gap, dnd, onGapDrop, children }: {
  gap: number; dnd: DragApi; onGapDrop: (gap: number, d: Drag) => void; children: ReactNode;
}) {
  return (
    <>
      <li className="flow-gap"><Gap index={gap} dnd={dnd} onGapDrop={onGapDrop} /></li>
      {children}
    </>
  );
}

function Gap({ index, dnd, onGapDrop, wide = false }: {
  index: number; dnd: DragApi; onGapDrop: (gap: number, d: Drag) => void; wide?: boolean;
}) {
  const id = `gap-${index}`;
  const active = dnd.drag !== null;
  const t = dnd.target(id, () => true, (d) => onGapDrop(index, d));
  return (
    <div className={`gap${active ? " active" : ""}${dnd.over === id ? " over" : ""}${wide ? " wide" : ""}`}
      aria-label={`${index + 1}번째 앞 틈`} {...t}>
      {active ? "+ 여기에 끼워 넣기" : ""}
    </div>
  );
}

function InsertForm({ count, call }: { count: number; call: Call }) {
  const [minutes, setMinutes] = useState("30");
  const [name, setName] = useState("");
  const [position, setPosition] = useState(String(count + 1));
  // 페이즈 수가 바뀌면 기본 위치는 다시 맨 끝이다.
  useEffect(() => setPosition(String(count + 1)), [count]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (await call("POST", "/phases/insert", { position: Number(position), 이름: name.trim() || null, 진행시간: Number(minutes) })) {
      setName("");
    }
  }

  return (
    <form onSubmit={submit} className="row start" aria-label="페이즈 추가">
      <label className="inline">
        페이즈 이름
        <input value={name} maxLength={100} placeholder="비우면 카드 이름으로 보임" onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="inline">
        진행 시간(분)
        <input type="number" min={0} max={1440} value={minutes} onChange={(e) => setMinutes(e.target.value)} />
      </label>
      <label className="inline">
        넣을 위치
        <select value={position} onChange={(e) => setPosition(e.target.value)}>
          {Array.from({ length: count + 1 }, (_, i) => (
            <option key={i} value={i + 1}>{i === count ? `맨 끝(${i + 1}번째)` : `${i + 1}번째 (지금 ${i + 1}번째는 뒤로 밀림)`}</option>
          ))}
        </select>
      </label>
      <button type="submit">페이즈 추가</button>
    </form>
  );
}

function PhaseCard({ ws, phase, index, total, phaseItems, gimmickItems, call, dnd, onDrop }: {
  ws: Workspace; phase: Row; index: number; total: number;
  phaseItems: LibraryItem[]; gimmickItems: LibraryItem[]; call: Call;
  dnd: DragApi; onDrop: (d: Drag) => void;
}) {
  const no = phase.순서 as number;
  const [time, setTime] = useState(String(phase.진행시간));
  const [name, setName] = useState(typeof phase.이름 === "string" ? phase.이름 : "");
  // 페이즈를 끼워 넣거나 옮기면 칸(key)은 그대로인 채 내용이 바뀌므로, 서버 값이 바뀌면 입력칸도 맞춘다.
  useEffect(() => {
    setTime(String(phase.진행시간));
    setName(typeof phase.이름 === "string" ? phase.이름 : "");
  }, [phase.이름, phase.진행시간]);
  const steps = rowsOf(ws, "phase-steps").filter((s) => s.진행순서_순서 === no);
  const uses = rowsOf(ws, "gimmick-uses").filter((u) => u.진행순서_순서 === no);
  const shown = typeof phase.이름 === "string" && phase.이름 ? phase.이름 : null;

  const id = `phase-${no}`;
  // 놓을 수 있는 것: 다른 페이즈(순서 바꾸기), 카드·기믹(붙이기·옮기기). 자기 칸에 이미 있는 칩은 받지 않는다.
  const t = dnd.target(id, (d) => !(d.kind === "phase" && d.order === no), onDrop);
  return (
    <li className={`phase${dnd.over === id ? " over" : ""}${dnd.drag?.kind === "phase" && dnd.drag.order === no ? " dragging" : ""}`}
      aria-label={`페이즈 ${index + 1}`} {...t}>
      <div className="row phase-head" draggable title="끌어서 페이즈 순서 바꾸기"
        onDragStart={(e) => dnd.start(e, { kind: "phase", order: no })} onDragEnd={dnd.end}>
        <strong>⠿ {index + 1}번째{shown ? ` · ${shown}` : ""}</strong>
        <span className="row start">
          <button type="button" className="small secondary" disabled={index === 0} aria-label={`페이즈 ${index + 1} 앞으로`}
            onClick={() => void call("POST", `/phases/${no}/move`, { position: index })}>
            ← 앞
          </button>
          <button type="button" className="small secondary" disabled={index === total - 1} aria-label={`페이즈 ${index + 1} 뒤로`}
            onClick={() => void call("POST", `/phases/${no}/move`, { position: index + 2 })}>
            뒤 →
          </button>
          <button type="button" className="small secondary" aria-label={`페이즈 ${index + 1} 삭제`}
            onClick={() => window.confirm(`${index + 1}번째 페이즈를 삭제할까요? 놓인 카드는 내려가고 뒤의 페이즈가 한 칸 앞으로 옵니다.`)
              && void call("DELETE", `/phases/${no}`)}>
            삭제
          </button>
        </span>
      </div>
      <div className="row start">
        <label className="inline">
          페이즈 이름
          <input value={name} maxLength={100} placeholder="비우면 카드 이름으로 보임" onChange={(e) => setName(e.target.value)} />
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
      <LinkedList title="진행단계" empty="붙은 진행단계가 없습니다." rows={steps} lib={ws.bundle.library.phases}
        libCol="진행단계_번호" items={phaseItems} resource="phase-steps" phaseNo={no} phaseLabel={index + 1} call={call} dnd={dnd} />
      <LinkedList title="기믹" empty="붙은 기믹이 없습니다." rows={uses} lib={ws.bundle.library.gimmicks}
        libCol="기믹_번호" items={gimmickItems} resource="gimmick-uses" phaseNo={no} phaseLabel={index + 1} call={call} dnd={dnd} />
    </li>
  );
}

function LinkedList({ title, empty, rows, lib, libCol, items, resource, phaseNo, phaseLabel, call, dnd }: {
  title: string; empty: string; rows: Row[]; lib: Record<string, LibraryRef>; libCol: string;
  items: LibraryItem[]; resource: string; phaseNo: number; phaseLabel: number; call: Call; dnd: DragApi;
}) {
  const [choice, setChoice] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const idCol = resource === "phase-steps" ? "번호" : "순서";
  const isCard = resource === "phase-steps";
  return (
    <div className="linked" role="group" aria-label={`페이즈 ${phaseLabel} ${title}`}>
      <span className="linked-title">{title}</span>
      {rows.length === 0 && <span className="muted">{empty}</span>}
      <ul className="chips">
        {rows.map((r) => {
          const ref = lib[String(r[libCol])];
          const id = r[idCol] as number;
          // 같은 카드가 둘 이상이면 서버가 계산해 둔 "1차 ○○" 이름을 쓴다.
          const base = (isCard && typeof r.표시이름 === "string" ? r.표시이름 : ref?.이름) ?? title;
          return (
            <li key={String(id)} className={`${ref?.삭제됨 ? "chip danger" : "chip accent"} draggable`} draggable
              onDragStart={(e) => dnd.start(e, { kind: isCard ? "chip-step" : "chip-gimmick", id })} onDragEnd={dnd.end}>
              {ref ? `${base} v${ref.버전}` : `#${String(r[libCol])}`}
              {ref?.삭제됨 && " · 삭제된 항목"}
              {r.설정 != null && <span className="muted"> · 설정 있음</span>}
              <button type="button" className="link" aria-label={`${base} 설정`} aria-expanded={editing === id}
                onClick={() => setEditing(editing === id ? null : id)}>
                설정
              </button>
              <button type="button" className="link" aria-label={`${base} 떼기`}
                onClick={() => void call("DELETE", `${resource}/${id}`)}>
                ×
              </button>
            </li>
          );
        })}
      </ul>
      {editing !== null && rows.some((r) => r[idCol] === editing) && (
        <SettingsEditor key={editing} resource={resource} id={editing} value={rows.find((r) => r[idCol] === editing)!.설정}
          showTab={isCard} call={call} onDone={() => setEditing(null)} />
      )}
      <div className="row start">
        <select aria-label={`${title} 선택`} value={choice} onChange={(e) => setChoice(e.target.value)}>
          <option value="">{title} 고르기…</option>
          {items.map((i) => (
            <option key={i.번호} value={i.번호}>{itemLabel(i)}</option>
          ))}
        </select>
        <button type="button" className="small" disabled={!choice}
          onClick={async () => {
            if (await call("POST", resource, { 진행순서_순서: phaseNo, [libCol]: Number(choice) })) setChoice("");
          }}>
          붙이기
        </button>
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
function SettingsEditor({ resource, id, value, showTab, call, onDone }: {
  resource: string; id: number; value: unknown; showTab: boolean; call: Call; onDone: () => void;
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
    if (await call("PATCH", `${resource}/${id}`, { 설정: Object.keys(next).length ? next : null })) onDone();
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
        <button type="button" className="small secondary" onClick={onDone}>닫기</button>
      </div>
    </div>
  );
}
