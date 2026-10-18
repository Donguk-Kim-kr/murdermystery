import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api, errorMessage, http } from "../api/client";
import type { components } from "../api/schema";
import { useAuth } from "../auth/AuthContext";
import { ConfirmPanel } from "../workspace/ConfirmPanel";
import { ContentPanel } from "../workspace/ContentPanel";
import { FlowReview, PhasesPanel } from "../workspace/PhasesPanel";
import { CharacterForm, type Character } from "./CharacterForm";
import { CommonStoryEditor } from "./CommonStoryEditor";
import { RoomPanel } from "./RoomPanel";
import { TestersPanel } from "./TestersPanel";
import { VisibilityPanel } from "./VisibilityPanel";
import { useConfirm } from "../confirm/ConfirmContext";
import { josa } from "../josa";
import { TIME_FORMATS, type TimeFormat } from "../timeFormat";

type Work = components["schemas"]["WorkOut"];

/**
 * 작업공간의 탭 (사용자 결정 2026-10-16). 게임 흐름이 중심이라 첫 탭이고 기본으로 열린다.
 *  - 인물(+관계 설정) / 장소(장소 구조) / 조사(단서·증언·조합의 설정과 위치)는 탭으로 둔다.
 *  - 공통 스토리·자료·엔딩·후일담은 진행단계 카드의 내용으로 옮길 예정이다.
 *  - 기본정보·공개·방·테스터는 마무리 단계(정리 탭)에서 한다.
 * 어느 탭부터 채워도 되고, 확인할 때만 검사한다.
 */
/** 마무리 단계 탭의 이름(가칭). 기본정보·흐름 검토·확정·공개·방·테스터가 모인다. 바꿀 때는 여기만 고친다. */
const FINISH_LABEL = "정리";
const TABS = [
  { id: "phases", label: "흐름" },
  { id: "characters", label: "인물" },
  { id: "places", label: "장소" },
  { id: "clues", label: "조사" },
  { id: "confirm", label: FINISH_LABEL },
] as const;
// 카드로 옮기기 전까지 내용을 편집할 곳이 없어지지 않게 구분선 뒤에 임시로 남겨 둔다. (사건·타임라인의 자리는 아직 미정)
const PENDING_TABS = [
  { id: "incidents", label: "사건" },
  { id: "relations", label: "자료" },
  { id: "endings", label: "결말" },
] as const;
const ALL_TABS = [...TABS, ...PENDING_TABS];
type TabId = (typeof ALL_TABS)[number]["id"];

export function WorkPage() {
  const confirm = useConfirm();
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
    if (!(await confirm(`${josa(`'${c.이름}'`, "을/를")} 삭제할까요?\n삭제된 내용은 복구할 수 없습니다.`))) return;
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
        <TitleEditor work={work} onSaved={load} />
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
      {tab === "clues" && <ContentPanel workId={workId} keys={["clues", "testimonies", "combos"]} />}
      {tab === "incidents" && <ContentPanel workId={workId} keys={["incidents", "incident-details", "timelines"]} />}
      {tab === "relations" && (
        <div className="stack">
          <CommonStoryEditor key={work.번호} work={work} onSaved={load} />
          <ContentPanel workId={workId} keys={["materials"]} />
        </div>
      )}
      {tab === "phases" && (
        <PhasesPanel workId={workId} />
      )}
      {tab === "endings" && <ContentPanel workId={workId} keys={["endings", "epilogues"]} />}
      {tab === "confirm" && (
        <div className="work-layout">
          <div className="col">
            <WorkInfoForm work={work} onSaved={load} />
            <FlowReview workId={workId} />
            <ConfirmPanel workId={workId} onConfirmed={load} />
          </div>
          <div className="col">
            <VisibilityPanel work={work} role={role} onChanged={load} />
            <RoomPanel work={work} />
            <TestersPanel workId={workId} />
          </div>
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
                        {c.NPC순위 != null && <span className="chip">NPC 가능 {c.NPC순위}순위</span>}
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
    </main>
  );
}

/**
 * 작품 제목: 머리글을 눌러 바로 고친다. Enter 나 다른 곳을 누르면 저장하고, Esc 는 취소한다.
 * 비운 채로 저장하지는 않는다(제목 칸은 비울 수 없다) — 이전 제목으로 되돌린다.
 */
function TitleEditor({ work, onSaved }: { work: Work; onSaved: () => Promise<void> }) {
  const [value, setValue] = useState(work.제목);
  const [error, setError] = useState<string | null>(null);
  const cancelled = useRef(false);   // Esc 로 취소했으면 이어지는 blur 에서 저장하지 않는다
  useEffect(() => setValue(work.제목), [work.제목]);   // 다른 곳(정리 탭의 기본정보)에서 바뀌면 따라간다

  async function save() {
    if (cancelled.current) {
      cancelled.current = false;
      setValue(work.제목);
      return;
    }
    const next = value.trim();
    if (next === "" || next === work.제목) {
      setValue(work.제목);
      return;
    }
    setError(null);
    const { error } = await api.PATCH("/api/works/{work_id}", { params: { path: { work_id: work.번호 } }, body: { 제목: next } });
    if (error) {
      setError(errorMessage(error, "제목을 저장하지 못했습니다"));
      setValue(work.제목);
    } else await onSaved();
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") e.currentTarget.blur();          // 저장은 blur 에서 한 번만 한다
    if (e.key === "Escape") {
      cancelled.current = true;
      e.currentTarget.blur();
    }
  }

  return (
    <h1 className="title-edit">
      <span className="title-sizer" aria-hidden="true">{value || " "}</span>
      <input aria-label="작품 제목" value={value} maxLength={100}
        onChange={(e) => setValue(e.target.value)} onBlur={() => void save()} onKeyDown={onKeyDown} />
      {error && <span role="alert" className="error title-error">{error}</span>}
    </h1>
  );
}

function WorkInfoForm({ work, onSaved }: { work: Work; onSaved: () => Promise<void> }) {
  const [title, setTitle] = useState(work.제목);
  useEffect(() => setTitle(work.제목), [work.제목]);   // 머리글에서 제목을 고치면 이 양식도 따라간다
  const [synopsis, setSynopsis] = useState(work.시놉시스);
  const [genre, setGenre] = useState(work.장르);
  const [time, setTime] = useState(work.예상시간);
  const [timeFormat, setTimeFormat] = useState<TimeFormat>(work.시간형식);
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
      body: { 제목: title, 시놉시스: synopsis, 장르: genre, 예상시간: time, 시간형식: timeFormat },
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
        <div className="field">
          <label>
            시간 형식
            <select value={timeFormat} onChange={(e) => setTimeFormat(e.target.value as TimeFormat)}>
              {TIME_FORMATS.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </label>
          <span className="hint">타임라인 같은 시간 칸을 어디까지 적을지 고릅니다.</span>
        </div>
        <div className="capacity">
          <span className="capacity-label">플레이 인원</span>
          <span className="chip accent">{work.최소인원 === work.최대인원 ? `${work.최대인원}명` : `${work.최소인원}~${work.최대인원}명`}</span>
          <span className="muted">
            인물에서 자동으로 계산됩니다. 최대는 NPC가 아닌 인물 수이고, 최소는 최대에서 "NPC가 될 수 있는 인물" 수를 뺀 값입니다
          </span>
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
