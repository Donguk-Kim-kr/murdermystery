import { useState } from "react";

import { api, errorMessage } from "../api/client";
import type { components } from "../api/schema";
import { canPublish, levelOnOwnWork, type Role } from "../visibility";

type Work = components["schemas"]["WorkOut"];

interface Props {
  work: Work;
  role: Role;
  onChanged: () => Promise<void>;
}

export function VisibilityPanel({ work, role, onChanged }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const level = levelOnOwnWork(role);
  const right = work.공개권한;

  async function act(action: "publish" | "unpublish" | "return-to-owner") {
    setBusy(true);
    setError(null);
    const { error } = await api.POST(`/api/works/{work_id}/${action}`, { params: { path: { work_id: work.번호 } } });
    setBusy(false);
    if (error) setError(errorMessage(error, "처리하지 못했습니다"));
    else await onChanged();
  }

  return (
    <section aria-label="공개 상태" className="card visibility">
      <h2>공개 상태</h2>
      {work.공개여부 ? (
        <>
          <p className="status-line">
            <span className="status-dot on" aria-hidden="true" />
            <span className="chip success">공개 중</span>
          </p>
          <button type="button" className="secondary" disabled={busy} onClick={() => void act("unpublish")}>
            비공개로 전환
          </button>
        </>
      ) : (
        <>
          <p className="status-line">
            <span className="status-dot" aria-hidden="true" />
            <span className="chip">비공개</span>
            {right !== "제작자" && <span className="chip warning">{right}가 비공개 처리했습니다.</span>}
          </p>
          {canPublish(right, level) ? (
            <div className="row start">
              <button type="button" disabled={busy || !work.확정버전_있음} onClick={() => void act("publish")}>
                공개하기
              </button>
              {right !== "제작자" && (
                <button type="button" className="secondary" disabled={busy} onClick={() => void act("return-to-owner")}>
                  제작자에게 공개 권한 돌려주기
                </button>
              )}
            </div>
          ) : (
            <p className="muted">
              제작자는 공개할 수 없습니다. {right}가 공개 권한을 제작자에게 돌려주면 다시 공개할 수 있습니다.
            </p>
          )}
        </>
      )}
      {!work.공개여부 && !work.확정버전_있음 && canPublish(right, level) && (
        <p className="muted">확정된 버전이 없어 공개할 수 없습니다.</p>
      )}
      {error && <p role="alert" className="error">{error}</p>}
    </section>
  );
}
