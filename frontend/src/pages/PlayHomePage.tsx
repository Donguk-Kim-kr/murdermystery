import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { components } from "../api/schema";
import { useConfirm } from "../confirm/ConfirmContext";
import { useRoom } from "../rooms/RoomContext";
import { JoinCodeDialog } from "./JoinRoomPage";

type PlayWork = components["schemas"]["PlayWorkOut"];

/** 로그인하면 처음 보이는 플레이공간: 내가 방을 만들 수 있는 작품과, 입장코드로 들어가는 버튼(누르면 코드 입력 창이 열린다). */
export function PlayHomePage() {
  const confirm = useConfirm();
  const { room, refresh } = useRoom();
  const [works, setWorks] = useState<PlayWork[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [joining, setJoining] = useState(false);

  async function leave() {
    setError(null);
    if (room!.내가_방장 && room!.상태 === "대기" && !(await confirm("방장이 나가면 방이 닫힙니다.\n나가시겠습니까?"))) return;
    const { error } = await api.POST("/api/rooms/leave");
    if (error) setError(errorMessage(error, "나가지 못했습니다"));
    await refresh();
  }

  useEffect(() => {
    let cancelled = false;
    api.GET("/api/play-works").then(({ data, error }) => {
      if (cancelled) return;
      if (data) setWorks(data);
      else setError(errorMessage(error, "작품 목록을 불러오지 못했습니다"));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="page">
      <div className="page-head">
        <h1>플레이</h1>
      </div>
      {room && (
        <section className="card" aria-label="내 방">
          <div className="row">
            <span>
              <strong>{room.작품.제목}</strong> - {room.상태 === "대기" ? "참여 중" : room.게임_종료 ? "종료" : "진행 중"}
            </span>
            <span className="row start">
              <Link to="/room" className="button">이동</Link>
              <button type="button" className="secondary" onClick={() => void leave()}>나가기</button>
            </span>
          </div>
        </section>
      )}
      <div className="row">
        <h2>게임 목록</h2>
        <button type="button" className="secondary" onClick={() => setJoining(true)}>입장코드</button>
      </div>
      {error && <p role="alert" className="error">{error}</p>}
      {works === null && !error && <p className="muted">불러오는 중…</p>}
      {works?.length === 0 && (
        <div className="empty">
          <strong>지금 플레이할 수 있는 작품이 없습니다.</strong>
          <p>공개된 작품이 생기면 여기에 나타납니다.</p>
        </div>
      )}
      {works && works.length > 0 && (
        <div className="work-grid">
          {works.map((w) => (
            <div key={w.번호} className="work-card">
              <h3>{w.제목}</h3>
              <p className="synopsis">{w.시놉시스 || "시놉시스가 아직 없습니다."}</p>
              <div className="work-meta">
                {w.비공개플레이 && <span className="chip accent">비공개 플레이</span>}
                <span className="chip">{w.장르 || "장르 미정"}</span>
                <span className="chip">인원 {w.최소인원}~{w.최대인원}명</span>
                <span className="chip">{w.예상시간}</span>
                <span className="chip">제작 {w.제작자}</span>
              </div>
              <Link to={`/rooms/new/${w.번호}`} state={{ title: w.제목 }} className="button small">방 만들기</Link>
            </div>
          ))}
        </div>
      )}
      {joining && <JoinCodeDialog onClose={() => setJoining(false)} />}
    </main>
  );
}
