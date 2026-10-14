import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { components } from "../api/schema";

type Work = components["schemas"]["WorkOut"];
type TestWork = components["schemas"]["TestableWorkOut"];

export function WorksListPage() {
  const [works, setWorks] = useState<Work[] | null>(null);
  const [testWorks, setTestWorks] = useState<TestWork[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.GET("/api/works").then(({ data, error }) => {
      if (cancelled) return;
      if (data) setWorks(data);
      else setError(errorMessage(error, "작품 목록을 불러오지 못했습니다"));
    });
    api.GET("/api/test-works").then(({ data }) => {
      if (!cancelled && data) setTestWorks(data);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // 내가 제작자인 작품은 위 목록에 있으므로, 남이 테스터로 지정해 준 작품만 따로 보여 준다.
  const mine = new Set((works ?? []).map((w) => w.번호));
  const others = testWorks.filter((w) => !mine.has(w.번호));

  return (
    <main className="page">
      <div className="row">
        <h1>내 작품</h1>
        <Link to="/works/new" className="button">새 작품</Link>
      </div>
      {error && <p role="alert" className="error">{error}</p>}
      {works === null && !error && <p>불러오는 중…</p>}
      {works?.length === 0 && <p className="muted">아직 작품이 없습니다.</p>}
      <ul className="list">
        {works?.map((w) => (
          <li key={w.번호}>
            <Link to={`/works/${w.번호}`}>
              <strong>{w.제목}</strong>
              <span className="muted">
                {w.장르 || "장르 미정"} · {w.상태} · {w.공개여부 ? "공개" : "비공개"} · 인원 {w.최소인원}~{w.최대인원}명
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {others.length > 0 && (
        <>
          <h2>테스트할 수 있는 작품</h2>
          <ul className="list">
            {others.map((w) => (
              <li key={w.번호}>
                <strong>{w.제목}</strong>
                <span className="muted"> {w.장르 || "장르 미정"} · 인원 {w.최소인원}~{w.최대인원}명</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </main>
  );
}
