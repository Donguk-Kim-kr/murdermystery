import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import { useRoom } from "../rooms/RoomContext";
import { SPACES } from "../spaces";

/** 서버가 진행 중인 방에 플레이어로 들어가려 할 때 돌려주는 안내. 이때는 관전으로 들어가는 버튼을 보인다. */
export const ROOM_IN_PROGRESS = "진행 중인 방입니다.";

/** 코드로 방에 들어가는 요청 하나. 성공하면 내 방 상태를 새로 읽고 방 화면으로 보낸다. 실패하면 안내 글을 돌려준다. */
function useEnterRoom() {
  const navigate = useNavigate();
  const { refresh } = useRoom();
  return async (code: string, observe = false): Promise<string | null> => {
    const { error } = await api.POST("/api/rooms/join", { body: { 입장코드: code, 관전: observe } });
    if (error) return errorMessage(error, "입장하지 못했습니다");
    await refresh();
    navigate("/room", { replace: true });
    return null;
  };
}

/** 입장 실패 안내. 진행 중인 방이면 관전으로 들어가는 버튼이 함께 나온다. */
function JoinProblem({ message, onObserve, busy }: { message: string; onObserve: () => void; busy: boolean }) {
  return (
    <>
      <p role="alert" className="error">{message}</p>
      {message === ROOM_IN_PROGRESS && <button type="button" className="secondary" disabled={busy} onClick={onObserve}>관전 참여</button>}
    </>
  );
}

/** 입장코드로 방에 들어가는 양식. 방 입장 페이지와 플레이공간 첫 화면의 입장 창이 함께 쓴다. */
export function JoinCodeForm({ plain = false, autoFocus = false }: { plain?: boolean; autoFocus?: boolean }) {
  const enter = useEnterRoom();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(observe: boolean) {
    setBusy(true);
    setError(null);
    const problem = await enter(code, observe);
    setBusy(false);
    if (problem) setError(problem);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void submit(false);
  }

  return (
    <form onSubmit={onSubmit} className={plain ? "join-plain" : "card"} aria-label="방 입장">
      {!plain && <h2>방 입장</h2>}
      {/* 창에서는 제목이 이미 "입장코드"라서 입력칸 위의 글자는 빼고, 스크린리더용 이름만 둔다 */}
      <label>
        {!plain && "입장코드"}
        <input
          className="code-input"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          maxLength={10}
          autoComplete="off"
          autoFocus={autoFocus}
          autoCapitalize="characters"
          spellCheck={false}
          aria-label={plain ? "입장코드" : undefined}
          required
        />
      </label>
      {error && <JoinProblem message={error} busy={busy} onObserve={() => void submit(true)} />}
      <button type="submit" disabled={busy}>입장하기</button>
    </form>
  );
}

/**
 * 방장이 준 링크(/join/코드)로 들어오면 바로 입장한다. 로그인하지 않았으면 로그인 화면이 먼저 나오고(이 경로는 그대로 남는다),
 * 로그인하면 이 페이지가 열려 바로 입장한다.
 */
export function JoinByLinkPage() {
  const { code = "" } = useParams();
  const enter = useEnterRoom();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const started = useRef(false);

  async function run(observe: boolean) {
    setBusy(true);
    setError(null);
    const problem = await enter(code, observe);
    if (problem) {
      setError(problem);
      setBusy(false);
    }
  }

  useEffect(() => {
    if (started.current) return;                    // 개발 모드에서 효과가 두 번 돌아도 입장은 한 번만 보낸다
    started.current = true;
    void run(false);
  }, []);                                           // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <main className="page narrow">
      <div className="card">
        <h1>방 입장</h1>
        {busy && !error && <p className="muted">입장하는 중…</p>}
        {error && <JoinProblem message={error} busy={busy} onObserve={() => void run(true)} />}
        {error && <Link to="/" className="back">← {SPACES.play}</Link>}
      </div>
    </main>
  );
}

/** 입장코드를 입력하는 작은 창. 바깥을 누르거나 Esc 를 누르면 닫힌다. */
export function JoinCodeDialog({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog join-dialog" role="dialog" aria-modal="true" aria-label="입장코드로 입장" onClick={(e) => e.stopPropagation()}>
        <div className="row">
          <h2>입장코드</h2>
          <button type="button" className="small secondary" onClick={onClose}>닫기</button>
        </div>
        <JoinCodeForm plain autoFocus />
      </div>
    </div>
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
