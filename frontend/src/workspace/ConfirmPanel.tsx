import { useCallback, useEffect, useState } from "react";

import { errorMessage, http } from "../api/client";
import { josa } from "../josa";

interface Check {
  errors: string[];
  warnings: string[];
  다음버전: string;
}
interface Version {
  번호: number;
  버전: string;
  생성일시: string;
  변경사항: string | null;
}

/** 확정: 지금 제작 내용을 그대로 복사해 한 버전으로 굳힌다. 만드는 도중에는 아무것도 막지 않고 여기서만 검사한다. */
export function ConfirmPanel({ workId, onConfirmed }: { workId: number; onConfirmed: () => void }) {
  const [check, setCheck] = useState<Check | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [c, v] = await Promise.all([
      http<Check>("GET", `/api/works/${workId}/confirm/check`),
      http<Version[]>("GET", `/api/works/${workId}/versions`),
    ]);
    if (c.data) setCheck(c.data);
    else setError(errorMessage(c.error, "검사하지 못했습니다"));
    setVersions(v.data ?? []);
  }, [workId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function confirm() {
    setBusy(true);
    setError(null);
    setDone(null);
    const res = await http<Version>("POST", `/api/works/${workId}/confirm`, note.trim() ? { 변경사항: note.trim() } : {});
    setBusy(false);
    if (res.error) setError(errorMessage(res.error, "확정하지 못했습니다"));
    else {
      setDone(`${josa(`버전 ${res.data!.버전}`, "을/를")} 확정했습니다.`);
      setNote("");
      await load();
      onConfirmed();
    }
  }

  if (!check) return error ? <p role="alert" className="error">{error}</p> : <p className="center">불러오는 중…</p>;
  return (
    <div className="stack">
      <section className="card" aria-label="확정 검사">
        <h2>확정하기</h2>
        <p className="muted">
          지금 만든 내용을 그대로 복사해 한 버전으로 굳힙니다. 확정한 뒤에도 계속 고칠 수 있고, 다시 확정하면 다음 버전이 됩니다.
          방은 확정된 최신 버전으로 만들어집니다.
        </p>
        {check.errors.length > 0 && (
          <div role="alert" className="error">
            <strong>확정하려면 해결해야 합니다</strong>
            <ul>{check.errors.map((m) => <li key={m}>{m}</li>)}</ul>
          </div>
        )}
        {check.warnings.length > 0 && (
          <div className="warn-box">
            <strong>확인해 보세요 (확정은 할 수 있습니다)</strong>
            <ul>{check.warnings.map((m) => <li key={m}>{m}</li>)}</ul>
          </div>
        )}
        {check.errors.length === 0 && check.warnings.length === 0 && <p className="ok">문제가 발견되지 않았습니다.</p>}
        <label>
          변경사항 (선택)
          <input value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
        </label>
        <div className="row start">
          <button type="button" disabled={busy || check.errors.length > 0} onClick={() => void confirm()}>
            {`버전 ${check.다음버전} 확정`}
          </button>
          <button type="button" className="secondary" onClick={() => void load()}>다시 검사</button>
        </div>
        {error && <p role="alert" className="error">{error}</p>}
        {done && <p role="status" className="ok">{done}</p>}
      </section>
      <section className="card" aria-label="확정된 버전">
        <h2>확정된 버전 <span className="muted">({versions.length})</span></h2>
        {versions.length === 0 && <p className="muted">아직 확정한 버전이 없습니다.</p>}
        <ul className="item-list">
          {versions.map((v) => (
            <li key={v.번호} className="item">
              <span className="order">{v.버전}</span>
              <span className="body">
                <span className="name">{new Date(v.생성일시).toLocaleString("ko-KR")}</span>
                {v.변경사항 && <span className="muted">{v.변경사항}</span>}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
