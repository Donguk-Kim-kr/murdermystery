import { useState, type FormEvent } from "react";

import { errorMessage, http } from "../api/client";
import { ConditionPicker } from "./ConditionPicker";
import {
  metaOf, refLabel, rowsOf, titleOf, useWorkspace,
  type FieldMeta, type Part, type ResourceMeta, type Row, type Workspace,
} from "./workspace";
import { josa } from "../josa";

/** 작업공간의 한 탭: 주어진 종류의 항목들을 목록과 입력 양식으로 보여 준다. 순서와 무관하게 아무거나 먼저 채울 수 있다. */
export function ContentPanel({ workId, keys }: { workId: number; keys: string[] }) {
  const { ws, error } = useWorkspace(workId);
  if (error) return <p role="alert" className="error">{error}</p>;
  if (!ws) return <p className="center">불러오는 중…</p>;
  return (
    <div className="stack">
      {ws.schema.resources
        .filter((r) => keys.includes(r.key) && !r.hidden)
        .sort((a, b) => keys.indexOf(a.key) - keys.indexOf(b.key))
        .map((meta) => (
          <ResourceSection key={meta.key} workId={workId} ws={ws} meta={meta} />
        ))}
    </div>
  );
}

export function ResourceSection({ workId, ws, meta }: { workId: number; ws: Workspace; meta: ResourceMeta }) {
  const rows = rowsOf(ws, meta.key);
  // null: 폼 닫힘, "new": 새 항목, 숫자: 그 항목 수정
  const [editing, setEditing] = useState<null | "new" | number>(null);
  const [error, setError] = useState<string | null>(null);

  async function remove(row: Row) {
    if (!window.confirm("이 항목을 삭제할까요?")) return;
    setError(null);
    const res = await http("DELETE", `/api/works/${workId}/content/${meta.key}/${row[meta.key_col]}`);
    if (res.error) setError(errorMessage(res.error, "삭제하지 못했습니다"));
    else await ws.reload();
  }

  const saved = async () => {
    setEditing(null);
    await ws.reload();
  };

  const sorted = meta.group_by
    ? [...rows].sort((a, b) => Number(a[meta.group_by!]) - Number(b[meta.group_by!]) || Number(a[meta.key_col]) - Number(b[meta.key_col]))
    : rows;

  return (
    <section className="card" aria-label={meta.label}>
      <div className="row">
        <h2>{meta.label} <span className="muted">({rows.length})</span></h2>
        {editing !== "new" && (
          <button type="button" className="small" onClick={() => setEditing("new")}>{`${meta.label} 추가`}</button>
        )}
      </div>
      {meta.help && <p className="muted">{meta.help}</p>}
      {rows.length === 0 && editing !== "new" && <p className="muted">아직 없습니다.</p>}
      <ul className="item-list">
        {sorted.map((row) => {
          const id = row[meta.key_col] as number;
          return (
            <li key={id}>
              {editing === id ? (
                <RowForm workId={workId} ws={ws} meta={meta} row={row} onSaved={saved} onCancel={() => setEditing(null)} />
              ) : (
                <div className="item">
                  <span className="order">{id}</span>
                  <span className="body">
                    <span className="name">{titleOf(meta.title_fields, row) ?? `${meta.label} ${id}`}</span>
                    <span className="muted">{summary(ws, meta, row)}</span>
                  </span>
                  <button type="button" className="small secondary" onClick={() => setEditing(id)}>편집</button>
                  <button type="button" className="small secondary" onClick={() => void remove(row)}>삭제</button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {error && <p role="alert" className="error">{error}</p>}
      {editing === "new" && (
        <RowForm workId={workId} ws={ws} meta={meta} onSaved={saved} onCancel={() => setEditing(null)} />
      )}
    </section>
  );
}

/** 목록 한 줄에 보여 줄 부가 설명: 제목이 아닌 칸 중 값이 있는 것들. */
function summary(ws: Workspace, meta: ResourceMeta, row: Row): string {
  const parts: string[] = [];
  for (const f of meta.fields) {
    const v = row[f.name];
    if (v === null || v === undefined || v === "" || meta.title_fields.includes(f.name)) continue;
    if (f.kind === "ref" && typeof v === "number") parts.push(`${f.label}: ${refLabel(ws, f.ref!, v)}`);
    else if (f.kind === "libref") continue;
    else if (f.kind === "json") parts.push(`${f.label}: ${JSON.stringify(v)}`.slice(0, 60));
    else if (f.kind === "text" || f.kind === "long") parts.push(`${f.label}: ${String(v).slice(0, 40)}`);
    else parts.push(`${f.label}: ${String(v)}`);
  }
  if (meta.has_parts) {
    const used = (row.재료 as Part[] | undefined) ?? [];
    parts.push(used.length === 0 ? "재료 없음" : `재료: ${used.map((p) => partLabel(ws, p)).join(", ")}`);
  }
  return parts.join(" · ");
}

const PART_KEYS: Record<Part["종류"], string> = { 단서: "clues", 증언: "testimonies", 조합: "combos" };
const PART_KINDS = Object.keys(PART_KEYS) as Part["종류"][];

const partLabel = (ws: Workspace, p: Part) => `${p.종류} ${refLabel(ws, PART_KEYS[p.종류], p.순서)}`;

type Draft = Record<string, string | boolean>;

function initialValue(f: FieldMeta, row?: Row): string | boolean {
  const v = row ? row[f.name] : f.default;
  if (f.kind === "bool") return Boolean(v);
  if (v === null || v === undefined) return "";
  if (f.kind === "json") return JSON.stringify(v);
  if (f.kind === "ts") return String(v).slice(0, 16);
  return String(v);
}

function toBody(fields: FieldMeta[], draft: Draft): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const f of fields) {
    const raw = draft[f.name];
    if (f.kind === "bool") body[f.name] = raw;
    else if (typeof raw === "string" && raw.trim() === "") body[f.name] = null;
    else if (f.kind === "int" || f.kind === "ref" || f.kind === "libref") body[f.name] = Number(raw);
    else if (f.kind === "json") body[f.name] = JSON.parse(String(raw));
    else body[f.name] = raw;
  }
  return body;
}

export function RowForm(props: {
  workId: number;
  ws: Workspace;
  meta: ResourceMeta;
  row?: Row;
  onSaved: () => void | Promise<void>;
  onCancel: () => void;
}) {
  const { workId, ws, meta, row, onSaved, onCancel } = props;
  const [draft, setDraft] = useState<Draft>(Object.fromEntries(meta.fields.map((f) => [f.name, initialValue(f, row)])));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fields = meta.fields.filter((f) => f.kind !== "libref"); // 진행단계·기믹 선택은 흐름 탭 전용 화면에서 한다
  const picksCondition = meta.key === "endings" || meta.key === "epilogues";       // 조건은 식을 쓰지 않고 진행단계가 내놓은 항목에서 고른다
  const [unfinished, setUnfinished] = useState(false);       // 조건 고르기가 덜 끝났다
  const [parts, setParts] = useState<Part[]>(((row?.재료 as Part[] | undefined) ?? []).map((p) => ({ 종류: p.종류, 순서: p.순서 })));

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (unfinished) {
      setError("조건 고르기를 끝내 주세요(빈칸이 있습니다). 필요 없는 조건은 지워 주세요");
      return;
    }
    let body: Record<string, unknown>;
    try {
      body = toBody(fields, draft);
    } catch {
      setError("JSON 형식이 올바르지 않습니다. 예: {}");
      return;
    }
    if (meta.has_parts) body.재료 = parts;
    setBusy(true);
    const base = `/api/works/${workId}/content/${meta.key}`;
    const res = row ? await http("PATCH", `${base}/${row[meta.key_col]}`, body) : await http("POST", base, body);
    setBusy(false);
    if (res.error) setError(errorMessage(res.error, "저장하지 못했습니다"));
    else await onSaved();
  }

  const set = (name: string, value: string | boolean) => setDraft({ ...draft, [name]: value });

  return (
    <form onSubmit={onSubmit} className="subform" aria-label={`${meta.label} ${row ? "수정" : "추가"}`}>
      <div className="field-grid two">
        {fields.map((f) =>
          picksCondition && f.name === "조건" ? (
            <ConditionPicker key={f.name} ws={ws} label={f.label} value={row ? row[f.name] : null}
              onChange={(value, complete) => {
                setUnfinished(!complete);
                set(f.name, value ? JSON.stringify(value) : f.required ? "{}" : "");
              }} />
          ) : (
            <FieldInput key={f.name} f={f} ws={ws} value={draft[f.name]} onChange={(v) => set(f.name, v)} />
          ),
        )}
      </div>
      {meta.has_parts && <PartsPicker ws={ws} parts={parts} onChange={setParts} selfOrder={row ? (row.순서 as number) : null} />}
      {error && <p role="alert" className="error">{error}</p>}
      <div className="row start">
        <button type="submit" disabled={busy}>저장</button>
        <button type="button" className="secondary" onClick={onCancel}>취소</button>
      </div>
    </form>
  );
}

function FieldInput({ f, ws, value, onChange }: {
  f: FieldMeta; ws: Workspace; value: string | boolean; onChange: (v: string | boolean) => void;
}) {
  const text = <span className={f.required ? "req-label" : undefined}>{f.label}</span>;
  const hint = f.help ? <span className="hint">{f.help}</span> : null;
  if (f.kind === "bool")
    return (
      <label className="check">
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
        {f.label}
      </label>
    );
  const wide = f.kind === "long" || f.kind === "json" ? "wide" : undefined;
  let control;
  if (f.kind === "long" || f.kind === "json")
    control = (
      <textarea rows={f.kind === "json" ? 2 : 3} value={String(value)} maxLength={f.max ?? undefined}
        spellCheck={f.kind === "json" ? false : undefined} onChange={(e) => onChange(e.target.value)} />
    );
  else if (f.kind === "ref") {
    const target = f.ref!;
    const ext = ws.schema.external.find((e) => e.key === target);
    const keyCol = ext?.key_col ?? metaOf(ws, target).key_col;
    control = (
      <select value={String(value)} onChange={(e) => onChange(e.target.value)}>
        <option value="">{f.required ? "선택…" : "(없음)"}</option>
        {rowsOf(ws, target).map((r) => (
          <option key={String(r[keyCol])} value={String(r[keyCol])}>{refLabel(ws, target, r[keyCol] as number)}</option>
        ))}
      </select>
    );
  } else if (f.kind === "int")
    control = <input type="number" value={String(value)} min={f.min ?? undefined} max={f.max ?? undefined} onChange={(e) => onChange(e.target.value)} />;
  else if (f.kind === "ts")
    control = <input type="datetime-local" value={String(value)} onChange={(e) => onChange(e.target.value)} />;
  else control = <input value={String(value)} maxLength={f.max ?? undefined} onChange={(e) => onChange(e.target.value)} />;
  return (
    <div className={wide ? "field wide" : "field"}>
      <label>
        {text}
        {control}
      </label>
      {hint}
    </div>
  );
}

/** 조합의 재료 고르기: 단서·증언·조합 버튼을 누르면 그 종류의 항목 목록이 나오고, 하나를 고르면 재료에 더해진다. 같은 재료는 한 번만 들어간다. */
function PartsPicker({ ws, parts, onChange, selfOrder }: {
  ws: Workspace; parts: Part[]; onChange: (parts: Part[]) => void; selfOrder: number | null;
}) {
  const [kind, setKind] = useState<Part["종류"] | null>(null);
  const has = (k: Part["종류"], order: number) => parts.some((p) => p.종류 === k && p.순서 === order);
  const choices = kind === null ? [] : rowsOf(ws, PART_KEYS[kind]).filter(
    (r) => !has(kind, r.순서 as number) && !(kind === "조합" && r.순서 === selfOrder),   // 자기 자신은 재료가 될 수 없다
  );

  function add(order: number) {
    if (kind !== null && !has(kind, order)) onChange([...parts, { 종류: kind, 순서: order }]);
  }

  return (
    <fieldset className="parts">
      <legend>재료</legend>
      {parts.length === 0 && <p className="muted">재료가 없습니다. 아래 버튼으로 단서·증언·조합을 골라 넣으세요.</p>}
      <ul className="item-list">
        {parts.map((p) => (
          <li key={`${p.종류}-${p.순서}`} className="item">
            <span className="body"><span className="name">{partLabel(ws, p)}</span></span>
            <button type="button" className="small secondary" aria-label={`재료에서 빼기: ${partLabel(ws, p)}`}
              onClick={() => onChange(parts.filter((q) => q !== p))}>빼기</button>
          </li>
        ))}
      </ul>
      <div className="row start" role="group" aria-label="재료 종류">
        {PART_KINDS.map((k) => (
          <button key={k} type="button" className={kind === k ? "small" : "small secondary"} aria-pressed={kind === k}
            onClick={() => setKind(kind === k ? null : k)}>
            {`${k} 넣기`}
          </button>
        ))}
      </div>
      {kind !== null && (
        <label>
          {`넣을 ${kind}`}
          <select value="" onChange={(e) => { if (e.target.value !== "") add(Number(e.target.value)); }}>
            <option value="">{choices.length === 0 ? `넣을 수 있는 ${josa(kind, "이/가")} 없습니다` : "선택…"}</option>
            {choices.map((r) => (
              <option key={String(r.순서)} value={String(r.순서)}>{refLabel(ws, PART_KEYS[kind], r.순서 as number)}</option>
            ))}
          </select>
        </label>
      )}
    </fieldset>
  );
}
