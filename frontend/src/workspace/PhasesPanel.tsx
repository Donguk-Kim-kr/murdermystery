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

type Call = (method: string, path: string, body?: unknown) => Promise<boolean>;

/** 칸에 놓은 카드·기믹의 세부 설정(`설정`)에서 다음 페이즈에도 탭을 남길지를 가리키는 키. 이름은 임시이며 엔진 설계에서 확정한다. */
const KEEP_TAB = "탭유지";

/**
 * 게임 흐름 화면: 페이즈(칸)를 순서대로 놓고, 칸마다 진행단계 카드와 기믹을 붙인다.
 * 페이즈는 끼워 넣거나 위아래로 옮길 수 있다 — 서버가 칸의 내용을 옮기므로 붙여 둔 카드·기믹·투표는 페이즈를 따라간다.
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

  /** 서버 호출 뒤 작업공간을 다시 읽는다. path 가 "/" 로 시작하면 그대로, 아니면 콘텐츠 경로로 본다. */
  const call: Call = async (method, path, body) => {
    setError(null);
    const url = path.startsWith("/") ? `/api/works/${workId}${path}` : `/api/works/${workId}/content/${path}`;
    const res = await http(method, url, body);
    if (res.error) setError(errorMessage(res.error, "처리하지 못했습니다"));
    else await ws.reload();
    return !res.error;
  };

  return (
    <section className="card" aria-label="페이즈">
      <h2>게임 흐름 <span className="muted">(페이즈 {phases.length}개)</span></h2>
      <p className="muted">
        페이즈를 순서대로 늘어놓고, 각 페이즈에 진행단계 카드와 기믹을 붙입니다. 카드와 기믹은{" "}
        <Link to="/library">라이브러리</Link>에서 만들어 둔 것을 고릅니다. 페이즈를 끼워 넣거나 옮기면 붙여 둔 내용도 함께 움직입니다.
      </p>
      {phases.length === 0 && <p className="muted">아직 페이즈가 없습니다.</p>}
      <ol className="item-list">
        {phases.map((p, i) => (
          <PhaseCard key={String(p.순서)} ws={ws} phase={p} index={i} total={phases.length}
            phaseItems={phaseItems} gimmickItems={gimmickItems} call={call} />
        ))}
      </ol>
      <InsertForm count={phases.length} call={call} />
      {error && <p role="alert" className="error">{error}</p>}
    </section>
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

function PhaseCard({ ws, phase, index, total, phaseItems, gimmickItems, call }: {
  ws: Workspace; phase: Row; index: number; total: number;
  phaseItems: LibraryItem[]; gimmickItems: LibraryItem[]; call: Call;
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

  return (
    <li className="phase" aria-label={`페이즈 ${index + 1}`}>
      <div className="row">
        <strong>{index + 1}번째{shown ? ` · ${shown}` : ""}</strong>
        <span className="row start">
          <button type="button" className="small secondary" disabled={index === 0} aria-label={`페이즈 ${index + 1} 위로`}
            onClick={() => void call("POST", `/phases/${no}/move`, { position: index })}>
            ↑ 위로
          </button>
          <button type="button" className="small secondary" disabled={index === total - 1} aria-label={`페이즈 ${index + 1} 아래로`}
            onClick={() => void call("POST", `/phases/${no}/move`, { position: index + 2 })}>
            ↓ 아래로
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
        libCol="진행단계_번호" items={phaseItems} resource="phase-steps" phaseNo={no} phaseLabel={index + 1} call={call} />
      <LinkedList title="기믹" empty="붙은 기믹이 없습니다." rows={uses} lib={ws.bundle.library.gimmicks}
        libCol="기믹_번호" items={gimmickItems} resource="gimmick-uses" phaseNo={no} phaseLabel={index + 1} call={call} />
    </li>
  );
}

function LinkedList({ title, empty, rows, lib, libCol, items, resource, phaseNo, phaseLabel, call }: {
  title: string; empty: string; rows: Row[]; lib: Record<string, LibraryRef>; libCol: string;
  items: LibraryItem[]; resource: string; phaseNo: number; phaseLabel: number; call: Call;
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
            <li key={String(id)} className={ref?.삭제됨 ? "chip danger" : "chip accent"}>
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
