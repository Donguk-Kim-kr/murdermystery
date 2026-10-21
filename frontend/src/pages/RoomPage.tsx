import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import { useNotice } from "../confirm/ConfirmContext";
import type { components } from "../api/schema";
import { GamePage } from "../game/GamePage";
import { josa } from "../josa";
import { useRoom } from "../rooms/RoomContext";

type RoomMember = components["schemas"]["MemberOut"];
type AiStatus = components["schemas"]["AiStatusOut"];

export function RoomPage() {
  const { room, refresh } = useRoom();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const notify = useNotice();
  const [starting, setStarting] = useState(false);
  const [ai, setAi] = useState<AiStatus | null>(null);               // 서버가 AI 추가를 허용하는지(방장의 대기실에서만 묻는다)
  const [aiBusy, setAiBusy] = useState(false);
  const [aiWaiting, setAiWaiting] = useState<string | null>(null);   // 방금 부른 AI 의 닉네임(방에 나타나면 안내를 거둔다)
  const hostWaiting = !!room && room.내가_방장 && room.상태 === "대기";

  useEffect(() => {
    if (!hostWaiting) return;
    let cancelled = false;
    api.GET("/api/ai/status").then(({ data }) => {
      if (cancelled || !data) return;
      setAi(data);
    }).catch(() => {});                                               // 연결이 끊기면 AI 추가 칸만 보이지 않는다
    return () => {
      cancelled = true;
    };
  }, [hostWaiting]);

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
    } catch {
      return;   // 복사 권한이 없으면 코드를 알려 준다
    }
    await notify("링크가 복사되었습니다.");
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

  async function patchSeat(body: { 플레이?: boolean; GM관전?: boolean; 계정_번호?: number }) {
    setError(null);
    const { error } = await api.PATCH("/api/rooms/me", { body });
    if (error) setError(errorMessage(error, "자리를 옮기지 못했습니다"));
    await refresh();
  }

  async function moveTo(accountId: number, playing: boolean) {
    const target = room!.참가자.find((m) => m.계정_번호 === accountId);
    if (!target || target.플레이 === playing) return;
    await patchSeat(accountId === room!.내_계정_번호 ? { 플레이: playing } : { 플레이: playing, 계정_번호: accountId });
  }

  async function toggleGm() {
    await patchSeat({ GM관전: !meObserver?.GM관전 });
  }

  async function addAi() {
    setError(null);
    setAiWaiting(null);
    setAiBusy(true);
    const { data, error } = await api.POST("/api/rooms/me/ai", { body: { 방식: "claude" } });
    if (error) setError(errorMessage(error, "AI 를 추가하지 못했습니다"));
    else if (data) setAiWaiting(data.닉네임);
    await refresh();
    setAiBusy(false);
  }

  async function startGame() {
    setError(null);
    setStarting(true);
    const { error } = await api.POST("/api/rooms/me/start");
    if (error) setError(errorMessage(error, "게임을 시작하지 못했습니다"));
    await refresh();
    setStarting(false);
  }

  const players = room.참가자.filter((m) => m.플레이);
  const observers = room.참가자.filter((m) => !m.플레이);
  const meObserver = observers.find((m) => m.계정_번호 === room.내_계정_번호);
  const meSeat = meObserver ? "관전" : "참가";

  // 방장은 다른 사람의 닉네임을 눌러 반대쪽으로 옮긴다. 방장 표시는 닉네임 바로 오른쪽의 왕관이다.
  function personName(m: RoomMember) {
    const canMove = room!.내가_방장 && m.계정_번호 !== room!.내_계정_번호;
    return (
      <span className="person-name">
        {canMove ? (
          <button type="button" className="link" title={m.플레이 ? "관전으로 옮기기" : "참가로 옮기기"} onClick={() => void moveTo(m.계정_번호, !m.플레이)}>
            {m.닉네임}
          </button>
        ) : (
          <span className="name">{m.닉네임}</span>
        )}
        {m.방장 && <span className="crown" role="img" aria-label="방장" title="방장">👑</span>}
      </span>
    );
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
            aria-label="링크 복사" title="링크 복사">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
            </svg>
          </button>
        </div>
      </div>

      <section aria-label="참가자" className="card">
        <div className="seat-head">
          <button type="button" className="seat-title" aria-pressed={meSeat === "참가"} onClick={() => void moveTo(room.내_계정_번호, true)}>
            참가
          </button>
          <span className="chip">{room.플레이어_수}/{room.작품.최대인원}명</span>
        </div>
        <ul className="person-list">
          {players.map((m) => (
            <li key={m.계정_번호} className="person">
              {personName(m)}
            </li>
          ))}
        </ul>
        <div className="seat-head">
          <button type="button" className="seat-title" aria-pressed={meSeat === "관전"} onClick={() => void moveTo(room.내_계정_번호, false)}>
            관전
          </button>
          <button type="button" className="small secondary" aria-label="관전 방식" disabled={meSeat !== "관전"} onClick={() => void toggleGm()}>
            {meObserver?.GM관전 ? "GM" : "일반"}
          </button>
        </div>
        <ul className="observer-list">
          {observers.map((m) => (
            <li key={m.계정_번호}>
              {personName(m)}
            </li>
          ))}
        </ul>
        {room.내가_방장 && ai?.사용가능 && (
          <div className="ai-add">
            <div className="row start">
              <button type="button" className="secondary" disabled={!ai.모델사용가능 || aiBusy || room.플레이어_수 >= room.작품.최대인원} onClick={() => void addAi()}>
                AI 추가
              </button>
              <span className="muted">{ai.모델}</span>
            </div>
            {!ai.모델사용가능 && <p className="muted">서버에 ANTHROPIC_API_KEY 가 없어 AI 를 부를 수 없습니다.</p>}
            {aiWaiting && !room.참가자.some((m) => m.닉네임 === aiWaiting) && (
              <p className="muted" role="status">{josa(aiWaiting, "이/가")} 입장하는 중입니다…</p>
            )}
          </div>
        )}
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
