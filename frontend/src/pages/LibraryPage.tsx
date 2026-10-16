import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { errorMessage, http } from "../api/client";
import { useAuth } from "../auth/AuthContext";

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

/** 진행단계·기믹 라이브러리. 같은 이름으로 만들면 그 계열의 다음 버전이 되고, 이름은 계열 전체를 한꺼번에 바꾼다. */
export function LibraryPage() {
  return (
    <main className="page">
      <Link to="/make" className="back">← 제작공간</Link>
      <h1>라이브러리</h1>
      <p className="muted">
        진행단계와 기믹은 여기서 한 번 만들어 두고 여러 작품의 페이즈에 붙여 씁니다. 만든 내용은 고치지 않고,
        같은 이름으로 다시 만들면 새 버전이 됩니다.
      </p>
      <div className="stack">
        {KINDS.map((k) => (
          <KindSection key={k.key} kind={k} />
        ))}
      </div>
    </main>
  );
}

function KindSection({ kind }: { kind: (typeof KINDS)[number] }) {
  const { state } = useAuth();
  const operator = state.status === "authenticated" && state.account.권한 === "운영자";
  const [items, setItems] = useState<Item[]>([]);
  const [showDeleted, setShowDeleted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ 이름: string; 설명: string; 변경내역: string; 공통: boolean; [c: string]: string | boolean }>(
    blank(kind),
  );
  const [renaming, setRenaming] = useState<{ id: number; name: string } | null>(null);

  const load = useCallback(async () => {
    const res = await http<Item[]>("GET", `/api/library/${kind.key}?include_deleted=${showDeleted}`);
    if (res.data) setItems(res.data);
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
    else await load();
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
    if (await act("POST", `/api/library/${kind.key}`, body)) setDraft(blank(kind));
  }

  const newVersionFrom = (i: Item) =>
    setDraft({
      이름: i.이름, 설명: i.설명 ?? "", 변경내역: "", 공통: i.공통,
      ...Object.fromEntries(kind.content.map((c) => [c, JSON.stringify(i[c])])),
    });

  return (
    <section className="card" aria-label={kind.label}>
      <div className="row">
        <h2>{kind.label}</h2>
        <label className="check">
          <input type="checkbox" checked={showDeleted} onChange={(e) => setShowDeleted(e.target.checked)} />
          삭제된 항목 보기
        </label>
      </div>
      <p className="muted">{kind.describe}</p>
      {lineages.size === 0 && <p className="muted">아직 없습니다.</p>}
      <ul className="item-list">
        {[...lineages.entries()].map(([k, versions]) => {
          const head = versions[0];
          const mayChange = !head.공통 || operator;
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
                  <strong>{head.이름} {head.공통 && <span className="chip accent">공통</span>}</strong>
                )}
                {mayChange && renaming?.id !== head.번호 && (
                  <span className="row start">
                    <button type="button" className="small secondary" onClick={() => setRenaming({ id: head.번호, name: head.이름 })}>이름 바꾸기</button>
                    <button type="button" className="small secondary"
                      onClick={() => window.confirm(`'${head.이름}'의 모든 버전을 삭제할까요?`) && void act("DELETE", `/api/library/${kind.key}/${head.번호}?scope=lineage`)}>
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
                        {kind.content.map((c) => <pre key={c}>{c}: {JSON.stringify(v[c], null, 1)}</pre>)}
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
      <form onSubmit={create} className="subform" aria-label={`${kind.label} 만들기`}>
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
        {operator && (
          <label className="check">
            <input type="checkbox" checked={draft.공통} onChange={(e) => setDraft({ ...draft, 공통: e.target.checked })} />
            공통 항목으로 만들기 (모든 제작자에게 보입니다)
          </label>
        )}
        <div className="row start"><button type="submit">만들기</button></div>
      </form>
      {error && <p role="alert" className="error">{error}</p>}
    </section>
  );
}

function blank(kind: (typeof KINDS)[number]) {
  return { 이름: "", 설명: "", 변경내역: "", 공통: false, ...Object.fromEntries(kind.content.map((c) => [c, "{}"])) };
}
