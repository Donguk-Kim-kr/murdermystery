import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { api, errorMessage } from "../api/client";
import type { components } from "../api/schema";

type Chat = components["schemas"]["ChatOut"];
type Message = components["schemas"]["ChatMessageOut"];
type Person = components["schemas"]["ChatMemberOut"];

const POLL_MS = import.meta.env.MODE === "test" ? 60 : 1500;

/** 대화에 보이는 이름: 캐릭터 이름(인물을 고르기 전에는 닉네임) */
const label = (p: Person): string => p.인물_이름 || p.닉네임;
const PALETTE = 8;                                      // 사람마다 글자 색이 다르다(styles.css 의 --chat-0 … --chat-7)

/**
 * 게임 채팅. 장소(전체·밀담 A …)가 있고, 플레이어는 한 번에 한 곳에만 있다. 장소를 누르면 그곳으로 옮기며, 그 장소에 있던 동안의 말만 보인다.
 * 관전자는 읽기만 한다(일반 관전은 전체만, GM 관전은 어느 장소든 골라 본다). 모든 사람의 위치는 장소 아래에 보인다.
 */
export function ChatPanel() {
  const [chat, setChat] = useState<Chat | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [watching, setWatching] = useState("전체");      // 관전자가 보고 있는 장소(플레이어는 자기 위치를 본다)
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [big, setBig] = useState(false);                  // 큰 창으로 보기(시연할 때 잘 보이도록)
  const last = useRef(0);
  const listRef = useRef<HTMLUListElement>(null);

  const load = useCallback(async () => {
    const { data } = await api.GET("/api/game/me/chat", { params: { query: { after: last.current } } });
    if (!data) return;
    setChat(data);
    if (data.메시지.length > 0) {
      last.current = data.메시지[data.메시지.length - 1].번호;
      setMessages((old) => [...old, ...data.메시지]);
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const player = chat?.내_위치 != null;
  const viewing = player ? chat!.내_위치! : watching;
  const shown = messages.filter((m) => m.장소 === viewing);
  useEffect(() => {
    listRef.current?.scrollTo?.({ top: listRef.current.scrollHeight });
  }, [shown.length, viewing, big]);
  useEffect(() => {
    if (!big) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setBig(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [big]);

  if (!chat) return <section className="card chat" aria-label="채팅"><h2>채팅</h2><p className="muted">불러오는 중…</p></section>;
  const gm = chat.역할 === "GM 관전";
  // 보낸 사람의 이름과 색: 지금 방에 있는 모든 사람(플레이어는 항상 어느 장소엔가 있다)을 계정 번호 순으로 세어 색을 정한다
  const people = new Map<number, Person>();
  chat.장소들.forEach((room) => room.사람들.forEach((p) => people.set(p.계정_번호, p)));
  const order = [...people.keys()].sort((a, b) => a - b);
  const colorOf = (account: number) => `chat-c${Math.max(0, order.indexOf(account)) % PALETTE}`;

  async function go(place: string) {
    setError(null);
    if (!player) {
      setWatching(place);
      return;
    }
    if (place === viewing) return;
    const { error } = await api.POST("/api/game/me/chat/move", { body: { 장소: place } });
    if (error) setError(errorMessage(error, "장소를 옮기지 못했습니다"));
    await load();
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const content = text.trim();
    if (!content || busy) return;
    setBusy(true);
    setError(null);
    const { error } = await api.POST("/api/game/me/chat/send", { body: { 내용: content } });
    if (error) setError(errorMessage(error, "보내지 못했습니다"));
    else setText("");
    setBusy(false);
    await load();
  }

  return (
    <>
    {big && <div className="overlay chat-backdrop" onClick={() => setBig(false)} />}
    <section className={`card chat${big ? " big" : ""}`} aria-label="채팅">
      <div className="row">
        <h2>채팅</h2>
        <button type="button" className="small secondary" aria-pressed={big} onClick={() => setBig(!big)}>
          {big ? "작게" : "크게 보기"}
        </button>
      </div>
      <ul className="chat-places" aria-label="채팅 장소">
        {chat.장소들.map((room) => {
          const here = room.이름 === viewing;
          const full = room.최대인원 !== null && room.사람들.length >= room.최대인원;
          const selectable = player ? !(full && !here) : gm || room.이름 === "전체";
          return (
            <li key={room.이름}>
              <button
                type="button"
                className={`chat-place${here ? " on" : ""}`}
                aria-pressed={here}
                disabled={!selectable}
                onClick={() => void go(room.이름)}
              >
                <span className="chat-place-name">{room.이름}</span>
                <span className="chat-place-people">
                  {room.사람들.length === 0 ? "비어 있음" : room.사람들.map((p, i) => (
                    <span key={p.계정_번호} className={colorOf(p.계정_번호)}>{i > 0 && ", "}{label(p)}</span>
                  ))}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <ul className="chat-log" aria-label={`${viewing} 대화`} ref={listRef}>
        {shown.length === 0 && <li className="muted">아직 대화가 없습니다.</li>}
        {shown.map((m) => (
          <li key={m.번호} className={`chat-msg ${colorOf(m.보낸이.계정_번호)}`}>
            <strong className="chat-name">{label(people.get(m.보낸이.계정_번호) ?? m.보낸이)}</strong>
            <span className="chat-text">{m.내용}</span>
          </li>
        ))}
      </ul>
      {error && <p role="alert" className="error">{error}</p>}
      {player && (
        <form className="chat-form" onSubmit={(e) => void submit(e)}>
          <input value={text} onChange={(e) => setText(e.target.value)} maxLength={500} aria-label="메시지" placeholder={`${viewing}에 말하기`} autoComplete="off" />
          <button type="submit" disabled={busy || text.trim() === ""}>보내기</button>
        </form>
      )}
    </section>
    </>
  );
}
