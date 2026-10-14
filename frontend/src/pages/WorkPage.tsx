import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { components } from "../api/schema";
import { useAuth } from "../auth/AuthContext";
import { CharacterForm, type Character } from "./CharacterForm";
import { RoomPanel } from "./RoomPanel";
import { TestersPanel } from "./TestersPanel";
import { VisibilityPanel } from "./VisibilityPanel";

type Work = components["schemas"]["WorkOut"];

export function WorkPage() {
  const workId = Number(useParams().id);
  const { state } = useAuth();
  const role = state.status === "authenticated" ? state.account.권한 : "사용자";
  const [work, setWork] = useState<Work | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  // null: 폼 닫힘, "new": 새 인물, 숫자: 그 순서의 인물 수정
  const [editing, setEditing] = useState<null | "new" | number>(null);

  const load = useCallback(async () => {
    const [w, c] = await Promise.all([
      api.GET("/api/works/{work_id}", { params: { path: { work_id: workId } } }),
      api.GET("/api/works/{work_id}/characters", { params: { path: { work_id: workId } } }),
    ]);
    if (w.data && c.data) {
      setWork(w.data);
      setCharacters(c.data);
    } else {
      setLoadError(errorMessage(w.error ?? c.error, "작품을 불러오지 못했습니다"));
    }
  }, [workId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loadError)
    return (
      <main className="page">
        <p role="alert" className="error">{loadError}</p>
        <Link to="/">목록으로</Link>
      </main>
    );
  if (!work) return <p className="center">불러오는 중…</p>;

  const closeForm = () => setEditing(null);
  const savedForm = () => {
    setEditing(null);
    void load();
  };

  return (
    <main className="page">
      <Link to="/" className="back">← 내 작품</Link>
      <div className="work-title">
        <h1>{work.제목}</h1>
        <span className={work.공개여부 ? "chip success" : "chip"}>{work.공개여부 ? "공개" : "비공개"}</span>
      </div>
      <div className="work-layout">
        <div className="col">
          <WorkInfoForm work={work} onSaved={load} />
          <section aria-label="인물 목록" className="card characters">
            <div className="row">
              <h2>인물 <span className="muted">({characters.length})</span></h2>
              {editing !== "new" && (
                <button type="button" className="small" onClick={() => setEditing("new")}>인물 추가</button>
              )}
            </div>
            {characters.length === 0 && editing !== "new" && <p className="muted">아직 인물이 없습니다.</p>}
            <ul className="person-list">
              {characters.map((c) => (
                <li key={c.순서}>
                  {editing === c.순서 ? (
                    <CharacterForm workId={workId} character={c} onCancel={closeForm} onSaved={savedForm} />
                  ) : (
                    <div className="person">
                      <span className="order">{c.순서}</span>
                      <span className="body">
                        <span className="name">{c.이름}</span>
                        {c.직업 && <span className="muted">{c.직업}</span>}
                      </span>
                      <span className="tags">
                        {c.NPC && <span className="chip">NPC</span>}
                        {c.범인 && <span className="chip danger">범인</span>}
                      </span>
                      <button type="button" className="small secondary" onClick={() => setEditing(c.순서)}>
                        편집
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
            {editing === "new" && <CharacterForm workId={workId} onCancel={closeForm} onSaved={savedForm} />}
          </section>
        </div>
        <div className="col">
          <VisibilityPanel work={work} role={role} onChanged={load} />
          <RoomPanel work={work} />
          <TestersPanel workId={workId} />
        </div>
      </div>
    </main>
  );
}

function WorkInfoForm({ work, onSaved }: { work: Work; onSaved: () => Promise<void> }) {
  const [title, setTitle] = useState(work.제목);
  const [synopsis, setSynopsis] = useState(work.시놉시스);
  const [genre, setGenre] = useState(work.장르);
  const [time, setTime] = useState(work.예상시간);
  const [minPlayers, setMinPlayers] = useState(String(work.최소인원));
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    const { error } = await api.PATCH("/api/works/{work_id}", {
      params: { path: { work_id: work.번호 } },
      body: { 제목: title, 시놉시스: synopsis, 장르: genre, 예상시간: time, 최소인원: Number(minPlayers) },
    });
    setBusy(false);
    if (error) setError(errorMessage(error, "저장하지 못했습니다"));
    else {
      setSaved(true);
      await onSaved();
    }
  }

  return (
    <form onSubmit={onSubmit} aria-label="기본정보" className="card info">
      <h2>기본정보</h2>
      <label>
        제목
        <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={100} required />
      </label>
      <label>
        시놉시스
        <textarea rows={4} value={synopsis} onChange={(e) => setSynopsis(e.target.value)} />
      </label>
      <div className="field-grid two">
        <label>
          장르
          <input value={genre} onChange={(e) => setGenre(e.target.value)} maxLength={50} />
        </label>
        <label>
          예상 시간
          <input value={time} onChange={(e) => setTime(e.target.value)} maxLength={50} required />
        </label>
        <label>
          최소 인원
          <input type="number" min={1} value={minPlayers} onChange={(e) => setMinPlayers(e.target.value)} required />
        </label>
        <div className="capacity">
          <span className="capacity-label">최대 인원</span>
          <span className="chip accent">{work.최대인원}명</span>
          <span className="muted">NPC가 아닌 인물 수로 자동 계산, 인물이 없으면 임시로 1명</span>
        </div>
      </div>
      {error && <p role="alert" className="error">{error}</p>}
      {saved && <p role="status" className="ok">저장했습니다.</p>}
      <div className="row start">
        <button type="submit" disabled={busy}>저장</button>
      </div>
    </form>
  );
}
