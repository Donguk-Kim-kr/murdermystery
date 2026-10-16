import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import { useRoom } from "../rooms/RoomContext";
import { SPACES } from "../spaces";

/** 입장코드로 방에 들어가는 양식. 방 입장 페이지와 플레이공간 첫 화면이 함께 쓴다. */
export function JoinCodeForm() {
  const navigate = useNavigate();
  const { refresh } = useRoom();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { error } = await api.POST("/api/rooms/join", { body: { 입장코드: code } });
    setBusy(false);
    if (error) {
      setError(errorMessage(error, "입장하지 못했습니다"));
      return;
    }
    await refresh();
    navigate("/room");
  }

  return (
    <form onSubmit={onSubmit} className="card" aria-label="방 입장">
      <h2>방 입장</h2>
      <label>
        입장코드
        <input
          className="code-input"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          maxLength={10}
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          placeholder="예: K7M2QX"
          required
        />
      </label>
      {error && <p role="alert" className="error">{error}</p>}
      <button type="submit" disabled={busy}>입장하기</button>
      <p className="muted">방장에게 받은 6자리 코드를 입력하세요.</p>
    </form>
  );
}

export function JoinRoomPage() {
  return (
    <main className="page narrow">
      <Link to="/" className="back">← {SPACES.play}</Link>
      <JoinCodeForm />
    </main>
  );
}
