import { useState } from "react";

import { api, errorMessage } from "../api/client";
import type { components } from "../api/schema";
import { useConfirm } from "../confirm/ConfirmContext";

type Work = components["schemas"]["WorkOut"];

// 공통 스토리도 개인 서사처럼 부분(최대 5)으로 나누어 쓴다. 전체 글자 수는 20000자이고 부분이 늘수록 각 부분의 제한이 줄어든다(서버 narrative.py 와 같은 규칙).
const MAX_PARTS = 5;
const TOTAL_LIMIT = 20000;
const partLimit = (count: number) => Math.floor(TOTAL_LIMIT / Math.max(count, 1));
const length = (text: string) => Array.from(text).length;

interface PartDraft {
  key: number;
  id: string | null;
  text: string;
}

/** 작품의 공통 스토리 편집. 어느 부분을 언제 보여 줄지는 흐름의 "공통 스토리" 카드 설정에서 번호로 고른다. */
export function CommonStoryEditor({ work, onSaved }: { work: Work; onSaved: () => void | Promise<void> }) {
  const confirm = useConfirm();
  const [parts, setParts] = useState<PartDraft[]>(() => {
    const saved = work.공통스토리_부분 ?? [];
    return (saved.length > 0 ? saved : [{ ID: null, 본문: "" }]).map((p, key) => ({ key, id: p.ID ?? null, text: p.본문 }));
  });
  const [nextKey, setNextKey] = useState(100);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  const limit = partLimit(parts.length);
  const nextLimit = partLimit(parts.length + 1);
  const overAfterAdd = parts.flatMap((p, i) => (length(p.text) > nextLimit ? [i + 1] : []));

  async function addPart() {
    if (parts.length >= MAX_PARTS) return;
    if (
      overAfterAdd.length > 0 &&
      !(await confirm(
        `공통 스토리를 ${parts.length + 1}개로 나누면 각 부분은 ${nextLimit}자까지 쓸 수 있습니다. ` +
          `지금 ${overAfterAdd.join(", ")}번째 부분이 넘으므로 줄여야 저장할 수 있습니다. 추가할까요?`,
      ))
    )
      return;
    setParts([...parts, { key: nextKey, id: null, text: "" }]);
    setNextKey(nextKey + 1);
    setSaved(false);
  }

  async function save() {
    setBusy(true);
    setError(null);
    const res = await api.PATCH("/api/works/{work_id}", {
      params: { path: { work_id: work.번호 } },
      // 비어 있는 부분 하나뿐이면 공통 스토리가 없는 것으로 저장한다
      body: { 공통스토리_부분: parts.length === 1 && parts[0].text.trim() === "" ? [] : parts.map((p) => ({ ID: p.id, 본문: p.text })) },
    });
    setBusy(false);
    if (res.error) setError(errorMessage(res.error, "공통 스토리를 저장하지 못했습니다"));
    else {
      const fresh = res.data?.공통스토리_부분 ?? [];
      if (fresh.length > 0) setParts(fresh.map((p, key) => ({ key, id: p.ID ?? null, text: p.본문 })));   // 서버가 붙인 부분 ID 를 이어받는다
      setNextKey(100);
      setSaved(true);
      await onSaved();
    }
  }

  return (
    <section className="card" aria-label="공통 스토리">
      <h2>공통 스토리</h2>
      <p className="muted">
        모든 플레이어가 함께 읽는 이야기입니다. 여러 부분으로 나누면 흐름의 "공통 스토리" 카드에서 보여 줄 부분을 골라, 예를 들어 처음에는 1부분을,
        1차 조사 뒤에는 2부분을 공개할 수 있습니다.
      </p>
      <div className="story-parts">
        {parts.map((p, i) => (
          <div key={p.key} className="story-part">
            <label>
              <span className="row">
                <span>공통 스토리 {i + 1}</span>
                <span className={length(p.text) > limit ? "error" : "muted"}>
                  {length(p.text)}/{limit}자
                </span>
              </span>
              <textarea
                rows={5}
                value={p.text}
                onChange={(e) => {
                  setParts(parts.map((q) => (q.key === p.key ? { ...q, text: e.target.value } : q)));
                  setSaved(false);
                }}
              />
            </label>
            {parts.length > 1 && (
              <button type="button" className="small secondary" onClick={() => { setParts(parts.filter((q) => q.key !== p.key)); setSaved(false); }}>
                공통 스토리 {i + 1} 삭제
              </button>
            )}
          </div>
        ))}
        <div className="row start">
          <button type="button" className="small secondary" disabled={parts.length >= MAX_PARTS} onClick={addPart}>
            부분 추가하기
          </button>
          <span className="muted">
            {parts.length >= MAX_PARTS
              ? `공통 스토리는 ${MAX_PARTS}개까지 나눌 수 있습니다.`
              : `${parts.length + 1}개로 나누면 각 부분은 ${nextLimit}자까지 쓸 수 있습니다.` +
                (overAfterAdd.length > 0 ? ` 지금 ${overAfterAdd.join(", ")}번째 부분이 넘습니다.` : "")}
          </span>
        </div>
      </div>
      {error && <p role="alert" className="error">{error}</p>}
      <div className="row start">
        <button type="button" disabled={busy} onClick={() => void save()}>공통 스토리 저장</button>
        {saved && <span className="muted" role="status">저장했습니다</span>}
      </div>
    </section>
  );
}
