import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import { useRoom } from "../rooms/RoomContext";

export function CreateRoomPage() {
  const workId = Number(useParams().workId);
  const navigate = useNavigate();
  const { refresh } = useRoom();
  const location = useLocation();
  const [title, setTitle] = useState<string | null>((location.state as { title?: string } | null)?.title ?? null);
  const [playing, setPlaying] = useState(true);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // 주소로 바로 들어왔으면 내가 비공개 플레이할 수 있는 작품 목록에서 제목을 찾는다.
  useEffect(() => {
    if (title !== null) return;
    let cancelled = false;
    api.GET("/api/private-play-works").then(({ data }) => {
      if (!cancelled) setTitle(data?.find((w) => w.번호 === workId)?.제목 ?? `작품 ${workId}`);
    });
    return () => {
      cancelled = true;
    };
  }, [title, workId]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    // 입장코드를 비워 두면 서버가 무작위로 만든다.
    const { error } = await api.POST("/api/rooms", { body: { 작품_번호: workId, 방장_참여: playing, 입장코드: code.trim() || null } });
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
        <p>
          <strong>{title ?? "…"}</strong> 으로 방을 만듭니다. 확정된 가장 최근 버전으로 진행됩니다.
        </p>
        <label>
          입장코드
          <input
            className="code-input"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            maxLength={10}
            autoComplete="off"
            spellCheck={false}
            placeholder="비워 두면 자동으로 만들어 줍니다"
          />
        </label>
        <p className="muted">
          참가자가 방에 들어올 때 입력하는 코드입니다. 4~10자의 영문·숫자·한글을 쓸 수 있고, 쉬운 코드는 다른 사람이 맞힐 수 있습니다.
          방이 끝나면 같은 코드를 다시 쓸 수 있습니다.
        </p>
        <label className="check">
          <input type="checkbox" checked={playing} onChange={(e) => setPlaying(e.target.checked)} />
          나도 플레이어로 참여
        </label>
        <p className="muted">
          끄면 방만 열고 배역은 맡지 않습니다. 제작자가 범인을 알고 있는 채로 플레이하고 싶지 않을 때 쓸 수 있습니다.
        </p>
        {error && <p role="alert" className="error">{error}</p>}
        <button type="submit" disabled={busy}>방 만들기</button>
      </form>
    </main>
  );
}
