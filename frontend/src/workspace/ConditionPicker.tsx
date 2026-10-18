import { useState } from "react";

import { rowsOf, type ArgDef, type ConditionDef, type LibraryRef, type Row, type Workspace } from "./workspace";

/**
 * 엔딩·후일담의 조건 고르기. 식은 진행단계 스크립트가 조건정의로 이미 정해 두었고, 여기서는 흐름에 놓인 카드의 조건 항목을 고르고
 * 빈칸(인물, 대상, 답 등)을 채울 뿐이다. 고른 것은 `{ "식": "…", "구성": [{카드, 조건, 인자}] }` 로 저장한다.
 * 여러 조건은 모두 맞아야 한다(그리고).
 */
export interface Pick {
  /** 진행구성 번호(흐름에 놓인 카드) */
  카드: number;
  조건: string;
  인자: Record<string, string | number>;
}

export interface Stored {
  식?: string;
  구성?: Pick[];
}

const asObject = (v: unknown): Record<string, unknown> =>
  v !== null && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};

interface Placed {
  step: Row;
  label: string;
  ref: LibraryRef;
}

/** 조건 항목을 가진 흐름의 카드들(흐름 순서대로). */
export function placedCards(ws: Workspace): Placed[] {
  const library = ws.bundle.library.phases;
  const steps = rowsOf(ws, "phase-steps");
  const order = new Map(rowsOf(ws, "phases").map((p, i) => [p.순서 as number, i]));
  return steps
    .filter((s) => (library[String(s.진행단계_번호)]?.조건정의 ?? []).length > 0)
    .sort((a, b) => (order.get(a.진행순서_순서 as number) ?? 0) - (order.get(b.진행순서_순서 as number) ?? 0) || (a.번호 as number) - (b.번호 as number))
    .map((step) => ({ step, label: String(step.표시이름 ?? "카드"), ref: library[String(step.진행단계_번호)] }));
}

/** 카드 설정 값. 정하지 않았으면 스크립트가 정한 기본값. */
function settingOf(placed: Placed, key: string): unknown {
  const set = asObject(placed.step.설정);
  if (key in set) return set[key];
  return placed.ref.설정정의?.find((d) => d.키 === key)?.기본;
}

const literal = (v: string | number) => (typeof v === "number" ? String(v) : JSON.stringify(v));

/** 식의 자리표시자를 고른 값으로 바꾼다: `{키}` 값(숫자나 따옴표 글), `{키:글}` 따옴표 없는 글, `{@설정키}` 카드 설정 값(글). */
export function renderExpression(def: ConditionDef, placed: Placed, args: Record<string, string | number>): string | null {
  let missing = false;
  const out = def.식.replace(/\{(@?)([^{}:]+)(:글)?\}/g, (_m, at: string, key: string, raw?: string) => {
    if (at) return String(settingOf(placed, key) ?? "");
    const v = args[key];
    if (v === undefined || v === "") {
      missing = true;
      return "";
    }
    return raw ? String(v) : literal(v);
  });
  return missing ? null : out;
}

export function composeCondition(ws: Workspace, picks: Pick[]): { value: Stored | null; complete: boolean } {
  const cards = placedCards(ws);
  const parts: string[] = [];
  let complete = true;
  for (const p of picks) {
    const placed = cards.find((c) => c.step.번호 === p.카드);
    const def = placed?.ref.조건정의?.find((d) => d.이름 === p.조건);
    const text = placed && def ? renderExpression(def, placed, p.인자) : null;
    if (text === null) complete = false;
    else parts.push(text);
  }
  if (picks.length === 0) return { value: null, complete: true };
  return { value: { 식: parts.map((t) => `(${t})`).join(" and "), 구성: picks }, complete };
}

export function ConditionPicker({ ws, value, onChange, label }: {
  ws: Workspace;
  value: unknown;
  onChange: (value: Stored | null, complete: boolean) => void;
  label: string;
}) {
  const stored = asObject(value) as Stored;
  const [cleared, setCleared] = useState(false);
  const codeOnly = !cleared && typeof stored.식 === "string" && stored.식.trim() !== "" && !Array.isArray(stored.구성);
  const [picks, setPicks] = useState<Pick[]>(Array.isArray(stored.구성) ? stored.구성 : []);
  const cards = placedCards(ws);

  function update(next: Pick[]) {
    setPicks(next);
    const { value: v, complete } = composeCondition(ws, next);
    onChange(v, complete);
  }

  if (codeOnly)
    return (
      <fieldset className="condition-picker wide">
        <legend>{label}</legend>
        <p className="muted">코드로 쓴 조건입니다: <code>{stored.식}</code></p>
        <button type="button" className="small secondary" onClick={() => { setCleared(true); update([]); }}>고르는 방식으로 바꾸기(조건을 지웁니다)</button>
      </fieldset>
    );

  return (
    <fieldset className="condition-picker wide">
      <legend>{label}</legend>
      {picks.length === 0 && <p className="muted">조건이 없으면 항상 나옵니다.</p>}
      {picks.map((pick, i) => (
        <PickRow key={i} ws={ws} cards={cards} index={i} pick={pick}
          onChange={(p) => update(picks.map((q, j) => (j === i ? p : q)))}
          onRemove={() => update(picks.filter((_, j) => j !== i))} />
      ))}
      {picks.length > 1 && <p className="muted">고른 조건이 모두 맞을 때 나옵니다.</p>}
      {cards.length === 0 ? (
        <p className="muted">고를 수 있는 조건이 없습니다. 조건을 내놓는 진행단계(최종 투표, 개인 질문, 능력 사용 …)를 흐름에 먼저 놓아 주세요.</p>
      ) : (
        <button type="button" className="small secondary" onClick={() => update([...picks, { 카드: cards[0].step.번호 as number, 조건: "", 인자: {} }])}>
          조건 더하기
        </button>
      )}
    </fieldset>
  );
}

function PickRow({ ws, cards, index, pick, onChange, onRemove }: {
  ws: Workspace; cards: Placed[]; index: number; pick: Pick; onChange: (p: Pick) => void; onRemove: () => void;
}) {
  const placed = cards.find((c) => c.step.번호 === pick.카드);
  const defs = placed?.ref.조건정의 ?? [];
  const def = defs.find((d) => d.이름 === pick.조건);
  const n = index + 1;
  return (
    <div className="pick-row" role="group" aria-label={`고른 조건 ${n}`}>
      {!placed && <p className="error">이 조건을 내놓던 카드가 흐름에서 사라졌습니다. 지우고 다시 골라 주세요.</p>}
      <label>
        {`조건 ${n} 카드`}
        <select value={String(pick.카드)} onChange={(e) => onChange({ 카드: Number(e.target.value), 조건: "", 인자: {} })}>
          {!placed && <option value={String(pick.카드)}>(사라진 카드)</option>}
          {cards.map((c) => <option key={String(c.step.번호)} value={String(c.step.번호)}>{c.label}</option>)}
        </select>
      </label>
      <label>
        {`조건 ${n}`}
        <select value={pick.조건} onChange={(e) => onChange({ ...pick, 조건: e.target.value, 인자: {} })}>
          <option value="">선택…</option>
          {pick.조건 !== "" && !def && <option value={pick.조건}>{`${pick.조건} (사라진 조건)`}</option>}
          {defs.map((d) => <option key={d.이름} value={d.이름}>{d.이름}</option>)}
        </select>
      </label>
      {placed && def && def.인자.map((arg) => (
        <ArgInput key={arg.키} ws={ws} placed={placed} arg={arg} args={pick.인자} n={n}
          onChange={(v) => {
            const next = { ...pick.인자, [arg.키]: v };
            if (arg.종류 === "질문인물") delete next[def.인자.find((a) => a.종류 === "질문답" && a.인물 === arg.키)?.키 ?? ""];   // 인물이 바뀌면 답을 다시 고른다
            onChange({ ...pick, 인자: next });
          }} />
      ))}
      <button type="button" className="small secondary" aria-label={`조건 ${n} 지우기`} onClick={onRemove}>지우기</button>
    </div>
  );
}

function ArgInput({ ws, placed, arg, args, n, onChange }: {
  ws: Workspace; placed: Placed; arg: ArgDef; args: Record<string, string | number>; n: number; onChange: (v: string | number) => void;
}) {
  const characters = rowsOf(ws, "characters");
  const label = `조건 ${n} ${arg.이름}`;
  const value = args[arg.키];
  const choose = (options: [string | number, string][], empty?: string) => (
    <label>
      {label}
      <select value={value === undefined ? "" : String(value)}
        onChange={(e) => { const found = options.find(([v]) => String(v) === e.target.value); if (found) onChange(found[0]); }}>
        <option value="">{empty ?? "선택…"}</option>
        {options.map(([v, t]) => <option key={String(v)} value={String(v)}>{t}</option>)}
      </select>
    </label>
  );

  switch (arg.종류) {
    case "인물":
      return choose(characters.map((c) => [c.순서 as number, String(c.이름)]));
    case "선택":
      return choose(arg.선택 ?? []);
    case "기타후보": {
      const raw = settingOf(placed, arg.설정 ?? "후보");
      const options = (Array.isArray(raw) ? raw : []).filter((v): v is string => typeof v === "string").map((v): [string, string] => [v, v]);
      return choose(options, options.length === 0 ? "이 카드에 인물이 아닌 후보가 없습니다" : undefined);
    }
    case "질문인물": {
      const questions = asObject(settingOf(placed, arg.설정 ?? "질문"));
      const asked = characters.filter((c) => questions[String(c.순서)] !== undefined);
      return choose(asked.map((c) => [c.순서 as number, String(c.이름)]), asked.length === 0 ? "이 카드에 질문이 정해진 인물이 없습니다" : undefined);
    }
    case "질문답": {
      const questions = asObject(settingOf(placed, arg.설정 ?? "질문"));
      const def = asObject(questions[String(args[arg.인물 ?? "인물"])]);
      const method = def.방식 ?? (Array.isArray(def.선택) && def.선택.length > 0 ? "선택" : "글");
      if (method === "인물") return choose(characters.map((c) => [c.순서 as number, String(c.이름)]));
      if (method === "장소") return choose(rowsOf(ws, "places").map((p): [string, string] => [`장소:${p.순서}`, String(p.이름)]));
      if (method === "선택" && Array.isArray(def.선택))
        return choose(def.선택.filter((c): c is string => typeof c === "string").map((c): [string, string] => [c, c]));
      return (
        <label>
          {label}
          <input value={value === undefined ? "" : String(value)} onChange={(e) => onChange(e.target.value)} placeholder="글로 답하는 질문입니다. 정확히 같은 답이어야 합니다" />
        </label>
      );
    }
    case "대상": {
      const kinds = settingOf(placed, arg.설정 ?? "대상");
      const allowed = Array.isArray(kinds) ? kinds : ["인물"];
      const options: [string | number, string][] = [];
      if (allowed.includes("인물")) for (const c of characters) options.push([c.순서 as number, `인물: ${c.이름}`]);
      if (allowed.includes("장소")) for (const p of rowsOf(ws, "places")) options.push([`장소:${p.순서}`, `장소: ${p.이름}`]);
      if (allowed.includes("단서")) for (const c of rowsOf(ws, "clues")) options.push([`단서:${c.순서}`, `단서: ${c.공개이름 || c.이름}`]);
      return choose(options);
    }
  }
}
