import { useCallback, useEffect, useState, type FormEvent } from "react";

import { api, errorMessage } from "../api/client";
import type { components } from "../api/schema";

type Tester = components["schemas"]["TesterOut"];

export function TestersPanel({ workId }: { workId: number }) {
  const [testers, setTesters] = useState<Tester[]>([]);
  const [loginId, setLoginId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const { data } = await api.GET("/api/works/{work_id}/testers", { params: { path: { work_id: workId } } });
    if (data) setTesters(data);
  }, [workId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function add(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const { error } = await api.POST("/api/works/{work_id}/testers", {
      params: { path: { work_id: workId } },
      body: { 아이디: loginId },
    });
    if (error) setError(errorMessage(error, "테스터를 추가하지 못했습니다"));
    else {
      setLoginId("");
      await load();
    }
  }

  async function remove(accountId: number) {
    setError(null);
    const { error } = await api.DELETE("/api/works/{work_id}/testers/{account_id}", {
      params: { path: { work_id: workId, account_id: accountId } },
    });
    if (error) setError(errorMessage(error, "테스터를 삭제하지 못했습니다"));
    else await load();
  }

  return (
    <section aria-label="테스터" className="panel">
      <h2>테스터 <span className="muted">({testers.length})</span></h2>
      <p className="muted">
        테스터는 이 작품이 공개 전이거나 제작자가 비공개한 동안에도 비공개 플레이(방 만들기)를 할 수 있습니다. 공개하지 않고 지인끼리 플레이할 때 쓰세요. 방 입장은 입장코드를 아는 사람이면 됩니다. 관리자·운영자가 비공개한 작품은 공개 권한이 제작자에게 돌아올 때까지 비공개 플레이를 할 수 없습니다.
      </p>
      <ul className="list">
        {testers.map((t) => (
          <li key={t.계정_번호} className="row">
            <span>{t.닉네임} <span className="muted">({t.아이디})</span></span>
            <button type="button" className="small secondary" onClick={() => void remove(t.계정_번호)}>
              삭제
            </button>
          </li>
        ))}
      </ul>
      <form onSubmit={add} className="row">
        <input
          aria-label="테스터 아이디"
          placeholder="아이디"
          value={loginId}
          onChange={(e) => setLoginId(e.target.value)}
          required
        />
        <button type="submit">추가</button>
      </form>
      {error && <p role="alert" className="error">{error}</p>}
    </section>
  );
}
