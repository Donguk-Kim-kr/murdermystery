import { useEffect, useMemo, useState } from "react";

import { BlockView, type Block } from "./Blocks";
import { ChatPanel } from "./ChatPanel";
import { useGame, type GameApi, type GameState } from "./useGame";

const NOW = "현재 화면";

function formatTime(total: number): string {
  const s = Math.max(0, Math.floor(total));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** 남은 시간. 서버가 상태를 만든 순간의 남은 초를 받아서 이 화면이 흐르는 시간만큼 줄인다(일시정지 중에는 줄이지 않는다). */
function useRemaining(state: GameState): number | null {
  const left = state.시간.남은_초;
  const received = useMemo(() => Date.now(), [state.상태_버전]);
  const running = left !== null && !state.시간.일시정지 && !state.시간.시간_종료;
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [running, state.상태_버전]);
  if (left === null) return null;
  return running ? Math.max(0, left - (now - received) / 1000) : left;
}

export function GamePage() {
  const game = useGame();
  const { state, missing } = game;
  if (missing)
    return (
      <main className="page narrow">
        <div className="empty">
          <strong>진행 중인 게임이 없습니다.</strong>
          <p>게임이 끝나 정리되었거나 이 방의 게임에 참여하지 않았습니다.</p>
        </div>
      </main>
    );
  if (!state) return <p className="center">게임을 불러오는 중…</p>;
  return <Play game={game} state={state} />;
}

function Play({ game, state }: { game: GameApi; state: GameState }) {
  const [tab, setTab] = useState(NOW);
  // 단계가 바뀌면 새 단계의 화면으로 돌아온다(지난 단계에서 읽던 탭에 머물러 있지 않는다)
  useEffect(() => setTab(NOW), [state.페이즈.순서]);
  const [dismissed, setDismissed] = useState(0);
  const remaining = useRemaining(state);
  const tabs = state.탭 as Block[];
  const shown = tabs.find((t) => t.이름 === tab);
  const selected = shown ? tab : NOW;
  const blocks = (selected === NOW ? state.화면 : [shown!]) as Block[];
  const notices = (state.알림 as { 번호: number; 글: string }[]).filter((n) => n.번호 > dismissed);
  const me = state.나;
  const canDrive = me.진행_권한;
  const lastPhase = state.페이즈.위치 >= state.페이즈.전체;

  return (
    <main className="page game">
      <header className="card game-head">
        <div className="row">
          <div className="work-meta">
            <span className="chip accent">
              {state.페이즈.위치}/{state.페이즈.전체}
            </span>
            <h1>{state.페이즈.이름 ?? "진행 중"}</h1>
          </div>
          <div className="work-meta">
            {state.종료 && <span className="chip warning">게임 종료</span>}
            {state.시간.일시정지 && <span className="chip warning">일시정지</span>}
            {remaining !== null && !state.종료 && (
              <span className={`chip${state.시간.시간_종료 ? " danger" : ""}`} aria-label="남은 시간">
                {state.시간.시간_종료 ? "시간 종료" : formatTime(remaining)}
              </span>
            )}
            <span className="chip">{me.역할 === "관전자" && me.관전방식 ? `${me.관전방식} 관전` : me.역할}</span>
          </div>
        </div>
        {!canDrive && <p className="muted">진행은 {state.권한.닉네임}님{state.권한.임시 ? "(임시)" : ""}이 맡고 있습니다.</p>}
        {canDrive && !state.종료 && <Controls game={game} state={state} lastPhase={lastPhase} />}
        {game.error && <p role="alert" className="error">{game.error}</p>}
      </header>

      {notices.map((n) => (
        <div key={n.번호} role="status" className="notice">
          <span>{n.글}</span>
          <button type="button" className="small secondary" onClick={() => setDismissed(Math.max(dismissed, n.번호))}>
            닫기
          </button>
        </div>
      ))}
      {(state.오류 as { 카드: string; 메시지: string }[]).map((e, i) => (
        <p key={i} role="alert" className="error">
          [{e.카드}] {e.메시지}
        </p>
      ))}

      <div className="game-body">
        <section className="card game-main" aria-label="화면">
          <div role="tablist" className="tabs">
            {[NOW, ...tabs.map((t) => String(t.이름))].map((name) => (
              <button
                key={name}
                type="button"
                role="tab"
                aria-selected={name === selected}
                className={name === selected ? "tab on" : "tab"}
                onClick={() => setTab(name)}
              >
                {name}
              </button>
            ))}
          </div>
          {blocks.length === 0 && <p className="muted">지금 보여 줄 내용이 없습니다.</p>}
          {blocks.map((block, i) => (
            <BlockView key={`${String(block.질문ID ?? block.이름)}-${i}`} block={block} state={state} onAnswer={game.answer} />
          ))}
        </section>

        <div className="game-side-col">
        <ChatPanel />
        <aside className="card game-side" aria-label="참가자">
          <h2>플레이어</h2>
          <ul className="person-list">
            {state.플레이어.map((p) => (
              <li key={p.계정_번호} className="person">
                <span className="body">
                  <span className="name">{p.닉네임}</span>
                  <span className="muted">{p.인물_이름 ?? "인물 미정"}</span>
                </span>
                <span className="tags">
                  {p.계정_번호 === state.권한.계정_번호 && <span className="chip accent">진행</span>}
                  {!p.접속중 && <span className="chip warning">자리 비움</span>}
                </span>
              </li>
            ))}
          </ul>
        </aside>
        </div>
      </div>
    </main>
  );
}

function Controls({ game, state, lastPhase }: { game: GameApi; state: GameState; lastPhase: boolean }) {
  const [busy, setBusy] = useState(false);
  const run = async (f: () => Promise<boolean>) => {
    setBusy(true);
    await f();
    setBusy(false);
  };
  return (
    <div className="row start" aria-label="진행">
      <button type="button" disabled={busy || lastPhase} onClick={() => void run(game.advance)}>
        다음 단계
      </button>
      {state.시간.남은_초 !== null && (
        <button type="button" className="secondary" disabled={busy} onClick={() => void run(() => game.pause(!state.시간.일시정지))}>
          {state.시간.일시정지 ? "시간 다시 흐르게" : "시간 멈추기"}
        </button>
      )}
      {state.나.방장 && (
        <>
          <label className="check">
            <input
              type="checkbox"
              checked={state.설정.자동_진행}
              onChange={(e) => void run(() => game.setAutoAdvance(e.target.checked))}
            />
            자동으로 넘기기
          </label>
          <label className="check">
            진행 맡기기
            <select
              value={state.권한.계정_번호}
              onChange={(e) => void run(() => game.giveAuthority(Number(e.target.value)))}
              aria-label="진행 권한"
            >
              {state.플레이어.map((p) => (
                <option key={p.계정_번호} value={p.계정_번호}>
                  {p.계정_번호 === state.나.계정_번호 ? `${p.닉네임} (나)` : p.닉네임}
                </option>
              ))}
              {!state.플레이어.some((p) => p.계정_번호 === state.나.계정_번호) && (
                <option value={state.나.계정_번호}>나 (관전)</option>
              )}
            </select>
          </label>
        </>
      )}
    </div>
  );
}
