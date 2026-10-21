import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { errorMessage, http } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ScriptEditor } from "./ScriptEditor";
import { useConfirm } from "../confirm/ConfirmContext";

interface Item {
  번호: number;
  이름: string;
  버전: number;
  설명: string | null;
  변경내역: string | null;
  삭제일시: string | null;
  공개여부: boolean;
  공통: boolean;
  [content: string]: unknown;
}

const KINDS = [
  { key: "phases", label: "진행단계", content: ["규칙"], describe: "한 페이즈 안에서 일어나는 일의 규칙(조사, 토론, 투표 …)" },
  { key: "gimmicks", label: "기믹", content: ["조건", "결과"], describe: "조건이 맞으면 결과가 일어나는 장치" },
] as const;

type Kind = (typeof KINDS)[number];
type CardKey = Kind["key"] | "functions";

// 라이브러리 카드. 함수는 화면만 있고 아직 서버에 없어서(목록도 만들기도 없다) 항상 비어 있다.
const CARDS: { key: CardKey; label: string; describe: string }[] = [
  ...KINDS.map((k) => ({ key: k.key, label: k.label, describe: k.describe })),
  { key: "functions", label: "함수", describe: "여러 진행단계와 기믹에서 불러 쓰는 코드" },
];

/** 라이브러리: 진행단계·기믹·함수 카드 셋 중 하나를 누르면 **내 계정이 만든** 항목만 보인다. 같은 이름으로 만들면 그 계열의 다음 버전이 되고, 이름은 계열 전체를 한꺼번에 바꾼다. */
export function LibraryPage() {
  const [selected, setSelected] = useState<CardKey>("phases");
  const [creating, setCreating] = useState(false);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const kind = KINDS.find((k) => k.key === selected);

  // 카드에 보이는 "내 항목 N개"(삭제하지 않은 것, 이름 하나가 한 계열)
  const loadCounts = useCallback(async () => {
    const next: Record<string, number> = { functions: 0 };
    for (const k of KINDS) {
      const res = await http<Item[]>("GET", `/api/library/${k.key}?include_deleted=false`);
      next[k.key] = res.data ? new Set(res.data.filter((i) => !i.공통).map((i) => i.이름)).size : 0;
    }
    setCounts(next);
  }, []);

  useEffect(() => {
    void loadCounts();
  }, [loadCounts]);

  return (
    <main className="page">
      <Link to="/make" className="back">← 제작공간</Link>
      <div className="page-head">
        <h1>라이브러리</h1>
        <button type="button" disabled={!kind} onClick={() => setCreating((v) => !v)}>새 라이브러리 만들기</button>
      </div>
      <div className="lib-cards">
        {CARDS.map((c) => (
          <button key={c.key} type="button" className="lib-card" aria-pressed={selected === c.key}
            onClick={() => { setSelected(c.key); setCreating(false); }}>
            <h2>{c.label}</h2>
            <p>{c.describe}</p>
            <span className="chip">내 {c.label} {counts[c.key] ?? 0}개</span>
          </button>
        ))}
      </div>
      {kind ? (
        <KindSection key={kind.key} kind={kind} creating={creating} onCreating={setCreating} onChanged={() => void loadCounts()} />
      ) : (
        <section className="card" aria-label="함수">
          <h2>함수</h2>
          <p className="muted">아직 없습니다.</p>
        </section>
      )}
    </main>
  );
}

function KindSection({ kind, creating, onCreating, onChanged }: { kind: Kind; creating: boolean; onCreating: (open: boolean) => void; onChanged: () => void }) {
  const confirm = useConfirm();
  const { state } = useAuth();
  const operator = state.status === "authenticated" && state.account.권한 === "운영자";
  const [items, setItems] = useState<Item[]>([]);
  const [showDeleted, setShowDeleted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ 이름: string; 설명: string; 변경내역: string; 공통: boolean; [c: string]: string | boolean }>(
    blank(kind),
  );
  // 진행단계만 스크립트 입력칸이 있다. 검사가 끝나 오류가 없을 때만 만들 수 있다.
  const [scriptOk, setScriptOk] = useState(true);
  const [renaming, setRenaming] = useState<{ id: number; name: string } | null>(null);

  const load = useCallback(async () => {
    const res = await http<Item[]>("GET", `/api/library/${kind.key}?include_deleted=${showDeleted}`);
    if (res.data) setItems(res.data.filter((i) => !i.공통));        // 내 계정이 만든 것만(공통 항목은 보이지 않는다)
    else setError(errorMessage(res.error, "불러오지 못했습니다"));
  }, [kind.key, showDeleted]);

  useEffect(() => {
    void load();
  }, [load]);

  // 같은 계열(공통 여부 + 이름)끼리 묶는다.
  const lineages = new Map<string, Item[]>();
  for (const i of items) {
    const k = `${i.공통 ? "공통" : "내"}|${i.이름}`;
    lineages.set(k, [...(lineages.get(k) ?? []), i]);
  }

  async function act(method: string, path: string, body?: unknown) {
    setError(null);
    const res = await http(method, path, body);
    if (res.error) setError(errorMessage(res.error, "처리하지 못했습니다"));
    else {
      await load();
      onChanged();
    }
    return !res.error;
  }

  async function create(e: FormEvent) {
    e.preventDefault();
    const body: Record<string, unknown> = {
      이름: draft.이름, 설명: draft.설명, 변경내역: draft.변경내역, 공통: draft.공통,
    };
    try {
      for (const c of kind.content) body[c] = JSON.parse(String(draft[c]) || "{}");
    } catch {
      setError("JSON 형식이 올바르지 않습니다. 예: {}");
      return;
    }
    if (kind.key === "phases") {
      const script = String(draft.스크립트 ?? "");
      if (script.trim() !== "") {
        if (typeof body.규칙 !== "object" || body.규칙 === null || Array.isArray(body.규칙)) {
          setError("규칙은 JSON 객체여야 스크립트와 함께 저장할 수 있습니다. 예: {}");
          return;
        }
        body.규칙 = { ...(body.규칙 as object), 스크립트: script };
      }
    }
    if (await act("POST", `/api/library/${kind.key}`, body)) {
      setDraft(blank(kind));
      onCreating(false);
    }
  }

  const newVersionFrom = (i: Item) => {
    const values = Object.fromEntries(kind.content.map((c) => [c, JSON.stringify(i[c])]));
    let script = "";
    if (kind.key === "phases" && typeof i.규칙 === "object" && i.규칙 !== null && !Array.isArray(i.규칙)) {
      // 스크립트는 따로 입력칸에서 고치고, 규칙(JSON)에는 나머지만 남긴다.
      const { 스크립트, ...rest } = i.규칙 as Record<string, unknown>;
      script = typeof 스크립트 === "string" ? 스크립트 : "";
      values.규칙 = JSON.stringify(rest);
    }
    setDraft({ 이름: i.이름, 설명: i.설명 ?? "", 변경내역: "", 공통: i.공통, ...values, 스크립트: script });
    onCreating(true);                                              // 만들기 양식이 열리고 이 버전의 내용이 채워진다
  };

  return (
    <section className="card" aria-label={kind.label}>
      {creating && (
        <form onSubmit={create} className="subform create-form" aria-label={`${kind.label} 만들기`}>
          <h3>{kind.label} 만들기</h3>
          <p className="muted">이미 있는 이름으로 만들면 그 이름의 다음 버전이 됩니다. 이름은 나중에 바꿀 수 있습니다.</p>
          <div className="field-grid two">
            <label>
              <span className="req-label">이름</span>
              <input value={draft.이름} maxLength={100} onChange={(e) => setDraft({ ...draft, 이름: e.target.value })} required />
            </label>
            <label>
              설명
              <input value={draft.설명} onChange={(e) => setDraft({ ...draft, 설명: e.target.value })} />
            </label>
            <label className="wide">
              변경내역 (새 버전일 때, 고를 때 함께 보입니다)
              <input value={draft.변경내역} onChange={(e) => setDraft({ ...draft, 변경내역: e.target.value })} />
            </label>
            {kind.content.map((c) => (
              <label key={c} className="wide">
                {c} (JSON)
                <textarea rows={3} spellCheck={false} value={String(draft[c])} onChange={(e) => setDraft({ ...draft, [c]: e.target.value })} />
              </label>
            ))}
          </div>
          {kind.key === "phases" && (
            <ScriptEditor value={String(draft.스크립트 ?? "")} onChange={(v) => setDraft({ ...draft, 스크립트: v })} onValid={setScriptOk} />
          )}
          {operator && (
            <label className="check">
              <input type="checkbox" checked={draft.공통} onChange={(e) => setDraft({ ...draft, 공통: e.target.checked })} />
              공통 항목으로 만들기 (모든 제작자에게 보입니다)
            </label>
          )}
          <div className="row start">
            <button type="submit" disabled={kind.key === "phases" && !scriptOk}>만들기</button>
            <button type="button" className="secondary" onClick={() => onCreating(false)}>취소</button>
          </div>
        </form>
      )}
      <div className="row">
        <h2>{kind.label}</h2>
        <label className="check">
          <input type="checkbox" checked={showDeleted} onChange={(e) => setShowDeleted(e.target.checked)} />
          삭제된 항목 보기
        </label>
      </div>
      {lineages.size === 0 && <p className="muted">아직 없습니다.</p>}
      <ul className="item-list">
        {[...lineages.entries()].map(([k, versions]) => {
          const head = versions[0];
          const mayChange = true;                                  // 내가 만든 항목만 보인다
          return (
            <li key={k} className="lineage" aria-label={`${kind.label} ${head.이름}`}>
              <div className="row">
                {renaming?.id === head.번호 ? (
                  <form className="row start" onSubmit={async (e) => { e.preventDefault(); if (await act("PATCH", `/api/library/${kind.key}/${head.번호}`, { 이름: renaming.name })) setRenaming(null); }}>
                    <input aria-label="새 이름" value={renaming.name} onChange={(e) => setRenaming({ id: head.번호, name: e.target.value })} />
                    <button type="submit" className="small">이름 바꾸기</button>
                    <button type="button" className="small secondary" onClick={() => setRenaming(null)}>취소</button>
                  </form>
                ) : (
                  <strong>{head.이름}</strong>
                )}
                {mayChange && renaming?.id !== head.번호 && (
                  <span className="row start">
                    <button type="button" className="small secondary" onClick={() => setRenaming({ id: head.번호, name: head.이름 })}>이름 바꾸기</button>
                    <button type="button" className="small secondary"
                      onClick={async () => (await confirm(`'${head.이름}'의 모든 버전을 삭제할까요?\n삭제된 내용은 복구할 수 없습니다.`)) && void act("DELETE", `/api/library/${kind.key}/${head.번호}?scope=lineage`)}>
                      계열 삭제
                    </button>
                  </span>
                )}
              </div>
              <ul className="versions">
                {versions.map((v) => (
                  <li key={v.번호} className={v.삭제일시 ? "version deleted" : "version"}>
                    <span className="chip">v{v.버전}</span>
                    {v.삭제일시 && <span className="chip danger">삭제됨</span>}
                    <span className="body">
                      <span>{v.설명 ?? ""}</span>
                      {v.변경내역 && <span className="muted">변경: {v.변경내역}</span>}
                      <details>
                        <summary>내용 보기</summary>
                        {kind.content.map((c) => <pre key={c}>{c}: {JSON.stringify(c === "규칙" ? withoutScript(v[c]) : v[c], null, 1)}</pre>)}
                        {kind.key === "phases" && scriptOf(v) && <pre aria-label="스크립트">{scriptOf(v)}</pre>}
                      </details>
                    </span>
                    {mayChange && !v.삭제일시 && (
                      <span className="row start">
                        <button type="button" className="small secondary" onClick={() => newVersionFrom(v)}>이 버전으로 새 버전 만들기</button>
                        <button type="button" className="small secondary" onClick={() => void act("DELETE", `/api/library/${kind.key}/${v.번호}`)}>삭제</button>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ul>
      {error && <p role="alert" className="error">{error}</p>}
    </section>
  );
}

function blank(kind: (typeof KINDS)[number]) {
  return { 이름: "", 설명: "", 변경내역: "", 공통: false, 스크립트: "", ...Object.fromEntries(kind.content.map((c) => [c, "{}"])) };
}

function scriptOf(item: Item): string {
  const rule = item.규칙;
  return typeof rule === "object" && rule !== null && typeof (rule as { 스크립트?: unknown }).스크립트 === "string"
    ? (rule as { 스크립트: string }).스크립트
    : "";
}

function withoutScript(rule: unknown): unknown {
  if (typeof rule !== "object" || rule === null || Array.isArray(rule)) return rule;
  const { 스크립트: _script, ...rest } = rule as Record<string, unknown>;
  return rest;
}
