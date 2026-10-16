import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, errorMessage } from "../api/client";

export function WorkNewPage() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { data, error } = await api.POST("/api/works", { body: { 제목: title.trim() } });
    setBusy(false);
    if (data) navigate(`/works/${data.번호}`);
    else setError(errorMessage(error, "작품을 만들지 못했습니다"));
  }

  return (
    <main className="page narrow">
      <Link to="/make/games" className="back">← 내 작품</Link>
      <form onSubmit={onSubmit} className="card">
        <h1>새 작품</h1>
        <label>
          제목
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={100} autoFocus placeholder="비워 두면 '제목 없는 작품'으로 만들어집니다" />
        </label>
        {error && <p role="alert" className="error">{error}</p>}
        <button type="submit" disabled={busy}>만들기</button>
        <p className="muted">제목은 비워 두거나 임시로 정해도 되고 나중에 바꿀 수 있습니다. 나머지는 만든 뒤 원하는 것부터 채우면 됩니다.</p>
      </form>
    </main>
  );
}
