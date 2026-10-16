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
    const { error } = await api.POST("/api/rooms", { body: { 작품_번호: workId, 방장_참여: playing } });
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
