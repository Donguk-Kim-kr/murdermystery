import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { api, errorMessage } from "../api/client";
import type { components } from "../api/schema";

type Chat = components["schemas"]["ChatOut"];
type Message = components["schemas"]["ChatMessageOut"];
type Person = components["schemas"]["ChatMemberOut"];

const POLL_MS = import.meta.env.MODE === "test" ? 60 : 1500;

function who(p: Person): string {
  return p.인물_이름 ? `${p.닉네임}(${p.인물_이름})` : p.닉네임;
}

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
  }, [shown.length, viewing]);

  if (!chat) return <section className="card chat" aria-label="채팅"><h2>채팅</h2><p className="muted">불러오는 중…</p></section>;
  const gm = chat.역할 === "GM 관전";

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
    <section className="card chat" aria-label="채팅">
      <h2>채팅</h2>
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
                  {room.사람들.length === 0 ? "비어 있음" : room.사람들.map((p) => p.닉네임).join(", ")}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <ul className="chat-log" aria-label={`${viewing} 대화`} ref={listRef}>
        {shown.length === 0 && <li className="muted">아직 대화가 없습니다.</li>}
        {shown.map((m) => (
          <li key={m.번호}>
            <strong>{who(m.보낸이)}</strong> <span>{m.내용}</span>
          </li>
        ))}
      </ul>
      {error && <p role="alert" className="error">{error}</p>}
      {player ? (
        <form className="chat-form" onSubmit={(e) => void submit(e)}>
          <input value={text} onChange={(e) => setText(e.target.value)} maxLength={500} aria-label="메시지" placeholder={`${viewing}에 말하기`} autoComplete="off" />
          <button type="submit" disabled={busy || text.trim() === ""}>보내기</button>
        </form>
      ) : (
        <p className="muted">{gm ? "GM 관전: 모든 장소의 대화를 볼 수 있고, 쓸 수는 없습니다." : "관전자는 전체 대화를 볼 수만 있습니다."}</p>
      )}
    </section>
  );
}
