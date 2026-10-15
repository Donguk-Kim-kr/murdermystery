import { useEffect, useState, type FormEvent } from "react";
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

/** 페이즈(진행 순서)를 만들고, 각 페이즈에 진행단계와 기믹을 붙이는 화면. 페이즈 번호는 만든 순서대로 붙고 바꿀 수 없다. */
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
  const [minutes, setMinutes] = useState("30");
  const [error, setError] = useState<string | null>(null);

  async function call(method: string, path: string, body?: unknown) {
    setError(null);
    const res = await http(method, `/api/works/${workId}/content/${path}`, body);
    if (res.error) setError(errorMessage(res.error, "처리하지 못했습니다"));
    else await ws.reload();
    return !res.error;
  }

  async function addPhase(e: FormEvent) {
    e.preventDefault();
    await call("POST", "phases", { 진행시간: Number(minutes) });
  }

  return (
    <section className="card" aria-label="페이즈">
      <h2>페이즈(진행 순서) <span className="muted">({phases.length})</span></h2>
      <p className="muted">
        페이즈 번호는 만든 순서대로 붙고 나중에 바꿀 수 없습니다. 진행단계와 기믹은{" "}
        <Link to="/library">라이브러리</Link>에서 만들어 둔 것을 골라 붙입니다.
      </p>
      {phases.length === 0 && <p className="muted">아직 페이즈가 없습니다.</p>}
      <ul className="item-list">
        {phases.map((p) => (
          <PhaseCard key={String(p.순서)} ws={ws} phase={p} phaseItems={phaseItems} gimmickItems={gimmickItems}
            call={call} />
        ))}
      </ul>
      <form onSubmit={addPhase} className="row start" aria-label="페이즈 추가">
        <label className="inline">
          진행 시간(분)
          <input type="number" min={0} max={1440} value={minutes} onChange={(e) => setMinutes(e.target.value)} />
        </label>
        <button type="submit">페이즈 추가</button>
      </form>
      {error && <p role="alert" className="error">{error}</p>}
    </section>
  );
}

function PhaseCard({ ws, phase, phaseItems, gimmickItems, call }: {
  ws: Workspace; phase: Row; phaseItems: LibraryItem[]; gimmickItems: LibraryItem[];
  call: (method: string, path: string, body?: unknown) => Promise<boolean>;
}) {
  const no = phase.순서 as number;
  const [time, setTime] = useState(String(phase.진행시간));
  const steps = rowsOf(ws, "phase-steps").filter((s) => s.진행순서_순서 === no);
  const uses = rowsOf(ws, "gimmick-uses").filter((u) => u.진행순서_순서 === no);

  return (
    <li className="phase" aria-label={`페이즈 ${no}`}>
      <div className="row">
        <strong>페이즈 {no}</strong>
        <span className="row start">
          <label className="inline">
            진행 시간(분)
            <input type="number" min={0} max={1440} value={time} onChange={(e) => setTime(e.target.value)} />
          </label>
          <button type="button" className="small secondary" onClick={() => void call("PATCH", `phases/${no}`, { 진행시간: Number(time) })}>
            시간 저장
          </button>
          <button type="button" className="small secondary"
            onClick={() => window.confirm(`페이즈 ${no}을(를) 삭제할까요?`) && void call("DELETE", `phases/${no}`)}>
            삭제
          </button>
        </span>
      </div>
      <LinkedList title="진행단계" empty="붙은 진행단계가 없습니다." rows={steps} lib={ws.bundle.library.phases}
        libCol="진행단계_번호" items={phaseItems} resource="phase-steps" phaseNo={no} call={call} />
      <LinkedList title="기믹" empty="붙은 기믹이 없습니다." rows={uses} lib={ws.bundle.library.gimmicks}
        libCol="기믹_번호" items={gimmickItems} resource="gimmick-uses" phaseNo={no} call={call} />
    </li>
  );
}

function LinkedList({ title, empty, rows, lib, libCol, items, resource, phaseNo, call }: {
  title: string; empty: string; rows: Row[]; lib: Record<string, LibraryRef>; libCol: string;
  items: LibraryItem[]; resource: string; phaseNo: number;
  call: (method: string, path: string, body?: unknown) => Promise<boolean>;
}) {
  const [choice, setChoice] = useState("");
  const idCol = resource === "phase-steps" ? "번호" : "순서";
  return (
    <div className="linked" role="group" aria-label={`페이즈 ${phaseNo} ${title}`}>
      <span className="linked-title">{title}</span>
      {rows.length === 0 && <span className="muted">{empty}</span>}
      <ul className="chips">
        {rows.map((r) => {
          const ref = lib[String(r[libCol])];
          return (
            <li key={String(r[idCol])} className={ref?.삭제됨 ? "chip danger" : "chip accent"}>
              {ref ? `${ref.이름} v${ref.버전}` : `#${String(r[libCol])}`}
              {ref?.삭제됨 && " · 삭제된 항목"}
              <button type="button" className="link" aria-label={`${ref?.이름 ?? title} 떼기`}
                onClick={() => void call("DELETE", `${resource}/${r[idCol]}`)}>
                ×
              </button>
            </li>
          );
        })}
      </ul>
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
