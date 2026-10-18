import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

type Ask = (message: string) => Promise<boolean>;

type Notify = (message: string) => Promise<void>;

const ConfirmContext = createContext<Ask | null>(null);
const NoticeContext = createContext<Notify | null>(null);

interface Pending {
  message: string;
  notice?: boolean;   // 알림: 확인 버튼 하나만 있다
  resolve: (ok: boolean) => void;
}

/**
 * 확인을 묻는 팝업. 브라우저 기본 확인 창(`window.confirm`) 대신 화면 안의 팝업으로 보인다.
 * 글에 줄바꿈이 있으면 줄마다 문단으로 나뉜다. 바깥을 누르거나 Esc 를 누르면 취소이다.
 */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);
  const current = useRef<Pending | null>(null);

  const open = useCallback((message: string, notice: boolean) => new Promise<boolean>((resolve) => {
    current.current?.resolve(false);                          // 앞의 물음이 아직 열려 있으면 취소로 닫는다
    const next = { message, notice, resolve };
    current.current = next;
    setPending(next);
  }), []);
  const ask = useCallback<Ask>((message) => open(message, false), [open]);
  const notify = useCallback<Notify>(async (message) => { await open(message, true); }, [open]);

  const answer = useCallback((ok: boolean) => {
    const open = current.current;
    if (!open) return;
    current.current = null;
    setPending(null);
    open.resolve(ok);
  }, []);

  useEffect(() => {
    if (!pending) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && answer(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pending, answer]);

  return (
    <ConfirmContext.Provider value={ask}>
      <NoticeContext.Provider value={notify}>
        {children}
        {pending && (
          <div className="overlay" onClick={() => answer(false)}>
            <div className="dialog confirm-dialog" role="alertdialog" aria-modal="true" aria-label={pending.notice ? "알림" : "확인"} onClick={(e) => e.stopPropagation()}>
              <div className="confirm-message">
                {pending.message.split("\n").map((line, i) => <p key={i}>{line}</p>)}
              </div>
              <div className="row end">
                {!pending.notice && <button type="button" className="secondary" onClick={() => answer(false)}>취소</button>}
                <button type="button" autoFocus onClick={() => answer(true)}>확인</button>
              </div>
            </div>
          </div>
        )}
      </NoticeContext.Provider>
    </ConfirmContext.Provider>
  );
}

/** `const confirm = useConfirm(); if (!(await confirm("…"))) return;` 처럼 쓴다. */
export function useConfirm(): Ask {
  const ask = useContext(ConfirmContext);
  if (!ask) throw new Error("ConfirmProvider 안에서만 쓸 수 있습니다");
  return ask;
}

/** `const notify = useNotice(); await notify("…");` — 확인 버튼 하나뿐인 알림 팝업. */
export function useNotice(): Notify {
  const notify = useContext(NoticeContext);
  if (!notify) throw new Error("ConfirmProvider 안에서만 쓸 수 있습니다");
  return notify;
}
