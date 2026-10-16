import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api, errorMessage, http } from "../api/client";
import type { components } from "../api/schema";
import { useAuth } from "../auth/AuthContext";
import { ConfirmPanel } from "../workspace/ConfirmPanel";
import { ContentPanel } from "../workspace/ContentPanel";
import { FlowReview, PhasesPanel } from "../workspace/PhasesPanel";
import { CharacterForm, type Character } from "./CharacterForm";
import { RoomPanel } from "./RoomPanel";
import { TestersPanel } from "./TestersPanel";
import { VisibilityPanel } from "./VisibilityPanel";

type Work = components["schemas"]["WorkOut"];

/**
 * 작업공간의 탭 (사용자 결정 2026-10-16). 게임 흐름이 중심이라 첫 탭이고 기본으로 열린다.
 *  - 인물(+관계 설정) / 장소(장소 구조) / 조사(단서·증언·조합의 설정과 위치)는 탭으로 둔다.
 *  - 공통 스토리·자료·엔딩·후일담은 진행단계 카드의 내용으로 옮길 예정이다.
 * 어느 탭부터 채워도 되고, 확인할 때만 검사한다.
 */
const TABS = [
  { id: "phases", label: "흐름" },
  { id: "characters", label: "인물" },
  { id: "places", label: "장소" },
  { id: "clues", label: "조사" },
  { id: "confirm", label: "확인" },
] as const;
// 카드로 옮기기 전까지 내용을 편집할 곳이 없어지지 않게 구분선 뒤에 임시로 남겨 둔다. (사건·타임라인의 자리는 아직 미정)
const PENDING_TABS = [
  { id: "overview", label: "개요" },
  { id: "incidents", label: "사건" },
  { id: "relations", label: "자료" },
  { id: "endings", label: "결말" },
] as const;
const ALL_TABS = [...TABS, ...PENDING_TABS];
type TabId = (typeof ALL_TABS)[number]["id"];

export function WorkPage() {
  const workId = Number(useParams().id);
  const { state } = useAuth();
  const role = state.status === "authenticated" ? state.account.권한 : "사용자";
  const [work, setWork] = useState<Work | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  // null: 폼 닫힘, "new": 새 인물, 숫자: 그 순서의 인물 수정
  const [editing, setEditing] = useState<null | "new" | number>(null);
  const [params, setParams] = useSearchParams();
  const tab: TabId = ALL_TABS.find((t) => t.id === params.get("tab"))?.id ?? "phases";
  const [deleteError, setDeleteError] = useState<string | null>(null);

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

  async function removeCharacter(c: Character) {
    if (!window.confirm(`'${c.이름}' 인물을 삭제할까요?`)) return;
    setDeleteError(null);
    const res = await http("DELETE", `/api/works/${workId}/characters/${c.순서}`);
    if (res.error) setDeleteError(errorMessage(res.error, "삭제하지 못했습니다"));
    else void load();
  }

  const closeForm = () => setEditing(null);
  const savedForm = () => {
    setEditing(null);
    void load();
  };

  return (
    <main className="page">
      <Link to="/make/games" className="back">← 내 작품</Link>
      <div className="work-title">
        <h1>{work.제목}</h1>
        <span className={work.공개여부 ? "chip success" : "chip"}>{work.공개여부 ? "공개" : "비공개"}</span>
      </div>
      <nav className="tabs" role="tablist" aria-label="작업공간">
        {[...TABS, null, ...PENDING_TABS].map((t, i) =>
          t === null ? (
            <span key="sep" className="tab-sep" aria-hidden="true" title="카드의 내용으로 옮길 예정(임시)" />
          ) : (
            <button key={t.id} type="button" role="tab" aria-selected={tab === t.id}
              className={`${tab === t.id ? "tab active" : "tab"}${i > TABS.length ? " pending" : ""}`}
              onClick={() => setParams(t.id === "phases" ? {} : { tab: t.id }, { replace: true })}>
              {t.label}
            </button>
          ),
        )}
      </nav>
      {tab === "places" && <ContentPanel workId={workId} keys={["places"]} />}
      {tab === "clues" && <ContentPanel workId={workId} keys={["clues", "testimonies", "combos", "combo-parts"]} />}
      {tab === "incidents" && <ContentPanel workId={workId} keys={["incidents", "incident-details", "timelines"]} />}
      {tab === "relations" && <ContentPanel workId={workId} keys={["materials"]} />}
      {tab === "phases" && (
        <div className="stack">
          <PhasesPanel workId={workId} />
          <ContentPanel workId={workId} keys={["votes"]} />
        </div>
      )}
      {tab === "endings" && <ContentPanel workId={workId} keys={["endings", "epilogues"]} />}
      {tab === "confirm" && (
        <div className="stack">
          <FlowReview workId={workId} />
          <ConfirmPanel workId={workId} onConfirmed={load} />
        </div>
      )}
      {tab === "characters" && (
        <div className="stack">
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
                      <button type="button" className="small secondary" onClick={() => void removeCharacter(c)}>
                        삭제
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
            {deleteError && <p role="alert" className="error">{deleteError}</p>}
            {editing === "new" && <CharacterForm workId={workId} onCancel={closeForm} onSaved={savedForm} />}
          </section>
          <ContentPanel workId={workId} keys={["relations"]} />
        </div>
      )}
      {tab === "overview" && (
      <div className="work-layout">
        <div className="col">
          <WorkInfoForm work={work} onSaved={load} />
        </div>
        <div className="col">
          <VisibilityPanel work={work} role={role} onChanged={load} />
          <RoomPanel work={work} />
          <TestersPanel workId={workId} />
        </div>
      </div>
      )}
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
      <p className="muted">제목은 임시로 정해도 됩니다. 나중에 언제든 바꿀 수 있습니다.</p>
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
