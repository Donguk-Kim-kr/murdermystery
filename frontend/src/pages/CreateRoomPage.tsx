import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import { useRoom } from "../rooms/RoomContext";

/** 방 만들기. 방장은 플레이어로 참여하는 것으로 시작하고, 관전으로 바꾸는 것은 방을 만든 뒤 대기실에서 한다. */
export function CreateRoomPage() {
  const workId = Number(useParams().workId);
  const navigate = useNavigate();
  const { refresh } = useRoom();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    // 입장코드를 비워 두면 서버가 무작위로 만든다.
    const { error } = await api.POST("/api/rooms", { body: { 작품_번호: workId, 방장_참여: true, 입장코드: code.trim() || null } });
    setBusy(false);
    if (error) {
      setError(errorMessage(error, "방을 만들지 못했습니다"));
      return;
    }
    await refresh();
    navigate("/room");
  }

  return (
    <main className="page narrow">
      <Link to="/" className="back">← 플레이공간</Link>
      <form onSubmit={onSubmit} className="card">
        <h1>방 만들기</h1>
        <label>
          입장코드
          <input
            className="code-input"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            maxLength={10}
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <p className="muted">
          입장 코드는 4~10자로 지정 가능합니다.<br />
          미 입력시 자동 생성됩니다.
        </p>
        {error && <p role="alert" className="error">{error}</p>}
        <button type="submit" disabled={busy}>방 만들기</button>
      </form>
    </main>
  );
}
