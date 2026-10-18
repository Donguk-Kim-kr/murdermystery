import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import { GamePage } from "../game/GamePage";
import { useRoom } from "../rooms/RoomContext";

export function RoomPage() {
  const { room, refresh } = useRoom();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [copiedLink, setCopiedLink] = useState(false);
  // 체크박스는 누르면 바로 바뀌고, 서버가 거부하면 원래대로 돌아간다 (서버 응답을 기다리면 반응이 느려 보인다).

  const [starting, setStarting] = useState(false);

  if (room === undefined) return <p className="center">불러오는 중…</p>;
  if (room !== null && room.상태 !== "대기") return <GamePage />;
  if (room === null)
    return (
      <main className="page narrow">
        <div className="empty">
          <strong>참여 중인 방이 없습니다.</strong>
          <p>방이 닫혔거나 나가셨습니다.</p>
          <Link to="/rooms/join" className="button">입장코드로 참여</Link>
        </div>
      </main>
    );

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/join/${encodeURIComponent(room!.입장코드)}`);
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 1500);
    } catch {
      /* 복사 권한이 없으면 코드를 알려 준다 */
    }
  }

  async function leave() {
    setError(null);
    const { error } = await api.POST("/api/rooms/leave");
    if (error) {
      setError(errorMessage(error, "나가지 못했습니다"));
      return;
    }
    await refresh();
    navigate("/");
  }

  async function startGame() {
    setError(null);
    setStarting(true);
    const { error } = await api.POST("/api/rooms/me/start");
    if (error) setError(errorMessage(error, "게임을 시작하지 못했습니다"));
    await refresh();
    setStarting(false);
  }

  return (
    <main className="page narrow">
      <div className="card">
        <div className="row room-title">
          <h1>{room.작품.제목}</h1>
          <span className="chip accent">대기 중</span>
        </div>
        <div className="code-box">
          <span className="muted">입장코드</span>
          <strong className="code" aria-label="입장코드">{room.입장코드}</strong>
          <button type="button" className="small secondary icon-btn" onClick={() => void copyLink()}
            aria-label={copiedLink ? "링크 복사됨" : "링크 복사"} title={copiedLink ? "링크 복사됨" : "링크 복사"}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              {copiedLink ? (
                <path d="M20 6 9 17l-5-5" />
              ) : (
                <>
                  <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                  <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
                </>
              )}
            </svg>
          </button>
        </div>
      </div>

      <section aria-label="참가자" className="card">
        <div className="row">
          <h2>참가자</h2>
          <span className="chip">
            플레이어 {room.플레이어_수}/{room.작품.최대인원}명
          </span>
        </div>
        <ul className="person-list">
          {room.참가자.map((m) => (
            <li key={m.계정_번호} className="person">
              <span className="order" aria-hidden="true">{m.닉네임.slice(0, 1)}</span>
              <span className="body">
                <span className="name">{m.닉네임}</span>
              </span>
              <span className="tags">
                {m.방장 && <span className="chip accent">방장</span>}
                <span className="chip">{m.플레이 ? "플레이" : "플레이 안 함"}</span>
              </span>
            </li>
          ))}
        </ul>
        {error && <p role="alert" className="error">{error}</p>}
        <div className="row center">
          {room.내가_방장 ? (
            <button type="button" disabled={starting} onClick={() => void startGame()}>
              게임 시작
            </button>
          ) : (
            <button type="button" className="secondary" onClick={() => void leave()}>
              나가기
            </button>
          )}
        </div>
      </section>
    </main>
  );
}
