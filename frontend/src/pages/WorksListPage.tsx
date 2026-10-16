import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, errorMessage, http } from "../api/client";
import type { components } from "../api/schema";
import { SPACES } from "../spaces";

type Work = components["schemas"]["WorkOut"];

export function WorksListPage() {
  const [works, setWorks] = useState<Work[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.GET("/api/works").then(({ data, error }) => {
      if (cancelled) return;
      if (data) setWorks(data);
      else setError(errorMessage(error, "작품 목록을 불러오지 못했습니다"));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function remove(w: Work) {
    if (!window.confirm(`'${w.제목}' 작품을 삭제할까요?\n인물·장소·단서·흐름 등 만들어 둔 내용이 모두 지워지고 되돌릴 수 없습니다.`)) return;
    setError(null);
    const res = await http("DELETE", `/api/works/${w.번호}`);
    if (res.error) setError(errorMessage(res.error, "삭제하지 못했습니다"));
    else {
      setWorks((list) => (list ?? []).filter((x) => x.번호 !== w.번호));
    }
  }

  return (
    <main className="page">
      <Link to="/make" className="back">← {SPACES.make}</Link>
      <div className="page-head">
        <h1>내 작품</h1>
        <Link to="/works/new" className="button">새 작품</Link>
      </div>
      {error && <p role="alert" className="error">{error}</p>}
      {works === null && !error && <p className="muted">불러오는 중…</p>}
      {works?.length === 0 && (
        <div className="empty">
          <strong>아직 작품이 없습니다.</strong>
          <p>첫 작품을 만들어 시나리오를 쓰기 시작하세요.</p>
          <Link to="/works/new" className="button">새 작품 만들기</Link>
        </div>
      )}
      {works && works.length > 0 && (
        <div className="work-grid">
          {works.map((w) => (
            <div key={w.번호} className="work-item">
              <Link to={`/works/${w.번호}`} className="work-card">
                <h3>{w.제목}</h3>
                <p className="synopsis">{w.시놉시스 || "시놉시스가 아직 없습니다."}</p>
                <div className="work-meta">
                  <span className={w.공개여부 ? "chip success" : "chip"}>{w.공개여부 ? "공개" : "비공개"}</span>
                  <span className="chip">{w.상태}</span>
                  <span className="chip">{w.장르 || "장르 미정"}</span>
                  <span className="chip">인원 {w.최소인원}~{w.최대인원}명</span>
                </div>
              </Link>
              <button type="button" className="small secondary work-delete" aria-label={`${w.제목} 삭제`} onClick={() => void remove(w)}>
                삭제
              </button>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
