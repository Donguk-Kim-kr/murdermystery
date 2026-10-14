import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { components } from "../api/schema";

type Work = components["schemas"]["WorkOut"];
type PrivatePlayWork = components["schemas"]["PrivatePlayWorkOut"];

export function WorksListPage() {
  const [works, setWorks] = useState<Work[] | null>(null);
  const [privateWorks, setPrivateWorks] = useState<PrivatePlayWork[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.GET("/api/works").then(({ data, error }) => {
      if (cancelled) return;
      if (data) setWorks(data);
      else setError(errorMessage(error, "작품 목록을 불러오지 못했습니다"));
    });
    api.GET("/api/private-play-works").then(({ data }) => {
      if (!cancelled && data) setPrivateWorks(data);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // 내가 제작자인 작품은 위 목록에 있으므로, 남이 테스터로 지정해 준 작품만 따로 보여 준다.
  const mine = new Set((works ?? []).map((w) => w.번호));
  const others = privateWorks.filter((w) => !mine.has(w.번호));

  return (
    <main className="page">
      <div className="page-head">
        <h1>내 작품</h1>
        <div className="row start">
          <Link to="/rooms/join" className="button secondary">방 입장</Link>
          <Link to="/works/new" className="button">새 작품</Link>
        </div>
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
            <Link key={w.번호} to={`/works/${w.번호}`} className="work-card">
              <h3>{w.제목}</h3>
              <p className="synopsis">{w.시놉시스 || "시놉시스가 아직 없습니다."}</p>
              <div className="work-meta">
                <span className={w.공개여부 ? "chip success" : "chip"}>{w.공개여부 ? "공개" : "비공개"}</span>
                <span className="chip">{w.상태}</span>
                <span className="chip">{w.장르 || "장르 미정"}</span>
                <span className="chip">인원 {w.최소인원}~{w.최대인원}명</span>
              </div>
            </Link>
          ))}
        </div>
      )}
      {others.length > 0 && (
        <>
          <h2>비공개 플레이 작품</h2>
          <div className="work-grid">
            {others.map((w) => (
              <div key={w.번호} className="work-card">
                <h3>{w.제목}</h3>
                <p className="synopsis">{w.시놉시스 || "시놉시스가 아직 없습니다."}</p>
                <div className="work-meta">
                  <span className="chip accent">테스터</span>
                  <span className="chip">{w.장르 || "장르 미정"}</span>
                  <span className="chip">인원 {w.최소인원}~{w.최대인원}명</span>
                </div>
                <Link to={`/rooms/new/${w.번호}`} state={{ title: w.제목 }} className="button small">
                  비공개 플레이 방 만들기
                </Link>
              </div>
            ))}
          </div>
        </>
      )}
    </main>
  );
}
