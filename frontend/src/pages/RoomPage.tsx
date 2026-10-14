import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import { useRoom } from "../rooms/RoomContext";

export function RoomPage() {
  const { room, refresh } = useRoom();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  // 체크박스는 누르면 바로 바뀌고, 서버가 거부하면 원래대로 돌아간다 (서버 응답을 기다리면 반응이 느려 보인다).
  const [pending, setPending] = useState<boolean | null>(null);

  if (room === undefined) return <p className="center">불러오는 중…</p>;
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

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(room!.입장코드);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* 복사 권한이 없으면 코드를 직접 선택해서 복사한다 */
    }
  }

  async function leave() {
    if (room!.내가_방장 && !window.confirm("방장이 나가면 방이 닫히고 모두 나가게 됩니다. 계속할까요?")) return;
    setError(null);
    const { error } = await api.POST("/api/rooms/leave");
    if (error) {
      setError(errorMessage(error, "나가지 못했습니다"));
      return;
    }
    await refresh();
    navigate("/");
  }

  async function togglePlaying(playing: boolean) {
    setError(null);
    setPending(playing);
    const { error } = await api.PATCH("/api/rooms/me", { body: { 플레이: playing } });
    if (error) setError(errorMessage(error, "바꾸지 못했습니다"));
    await refresh();
    setPending(null);
  }

  const hostPlaying = room.참가자.find((m) => m.방장)?.플레이 ?? false;

  return (
    <main className="page narrow">
      <div className="card">
        <div className="work-meta">
          <span className="chip accent">대기 중</span>
          <span className="chip">버전 {room.버전}</span>
        </div>
        <h1>{room.작품.제목}</h1>
        <div className="code-box">
          <span className="muted">입장코드</span>
          <strong className="code" aria-label="입장코드">{room.입장코드}</strong>
          <button type="button" className="small secondary" onClick={() => void copyCode()}>
            {copied ? "복사됨" : "복사"}
          </button>
        </div>
        <p className="muted">이 코드를 아는 사람은 누구나 입장할 수 있습니다. 함께할 사람에게만 알려 주세요.</p>
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
        <p className="muted">
          최소 {room.작품.최소인원}명이 모여야 시작할 수 있습니다. 배역 선택과 게임 시작은 아직 준비 중입니다.
        </p>
        {room.내가_방장 && (
          <label className="check">
            <input type="checkbox" checked={pending ?? hostPlaying} onChange={(e) => void togglePlaying(e.target.checked)} />
            나도 플레이어로 참여
          </label>
        )}
        {error && <p role="alert" className="error">{error}</p>}
        <div className="row start">
          <button type="button" className="secondary" onClick={() => void leave()}>
            {room.내가_방장 ? "방 닫기" : "나가기"}
          </button>
        </div>
      </section>
    </main>
  );
}
