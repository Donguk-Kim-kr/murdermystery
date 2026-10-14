import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

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
    const { data, error } = await api.POST("/api/works", { body: { 제목: title } });
    setBusy(false);
    if (data) navigate(`/works/${data.번호}`);
    else setError(errorMessage(error, "작품을 만들지 못했습니다"));
  }

  return (
    <main className="page narrow">
      <h1>새 작품</h1>
      <form onSubmit={onSubmit}>
        <label>
          제목
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={100} required autoFocus />
        </label>
        {error && <p role="alert" className="error">{error}</p>}
        <button type="submit" disabled={busy}>만들기</button>
      </form>
      <p className="muted">시놉시스·장르·인물은 만든 뒤에 입력합니다.</p>
    </main>
  );
}
