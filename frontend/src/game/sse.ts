import { getToken } from "../api/token";

export interface SseEvent {
  event: string;
  data: string;
}

/**
 * SSE 본문을 조각 단위로 받아 이벤트로 나눈다. 조각이 줄 중간에서 끊겨도 이어 붙이고,
 * `:` 로 시작하는 줄(연결 유지 신호)은 버린다.
 */
export function createSseParser(onEvent: (e: SseEvent) => void): (chunk: string) => void {
  let buffer = "";
  let event = "message";
  let data: string[] = [];

  const flush = () => {
    if (data.length > 0) onEvent({ event, data: data.join("\n") });
    event = "message";
    data = [];
  };

  return (chunk) => {
    buffer += chunk;
    let at: number;
    while ((at = buffer.search(/\r\n|\n|\r/)) >= 0) {
      const line = buffer.slice(0, at);
      buffer = buffer.slice(at + (buffer.startsWith("\r\n", at) ? 2 : 1));
      if (line === "") flush();
      else if (line.startsWith(":")) continue;
      else {
        const colon = line.indexOf(":");
        const field = colon < 0 ? line : line.slice(0, colon);
        const value = colon < 0 ? "" : line.slice(colon + 1).replace(/^ /, "");
        if (field === "event") event = value;
        else if (field === "data") data.push(value);
      }
    }
  };
}

export interface EventsOptions {
  /** 서버가 보낸 상태 버전. 연결(재연결 포함)할 때마다 현재 버전을 한 번 먼저 받는다. */
  onVersion(version: number): void;
  /** 게임이 없어졌거나(404) 서버가 닫았다고 알렸다. 더 이상 다시 연결하지 않는다. */
  onClosed(): void;
  signal: AbortSignal;
  retryMs?: number;
}

/**
 * 게임의 변화 알림(SSE)을 `fetch` 로 읽는다. 일반 요청과 같은 `Authorization` 헤더를 쓰기 위해 EventSource 를 쓰지 않는다.
 * 끊기면 잠시 뒤 다시 연결한다(재연결하면 최신 버전을 먼저 받으므로 놓친 변화가 없다).
 */
export async function connectEvents({ onVersion, onClosed, signal, retryMs = 1500 }: EventsOptions): Promise<void> {
  let delay = retryMs;
  while (!signal.aborted) {
    try {
      const headers = new Headers({ Accept: "text/event-stream" });
      const token = getToken();
      if (token) headers.set("Authorization", `Bearer ${token}`);
      const res = await fetch(new Request(new URL("/api/game/me/events", window.location.origin), { headers, signal }));
      if (res.status === 404 || res.status === 401) {
        onClosed();
        return;
      }
      if (res.ok && res.body) {
        delay = retryMs;
        let closed = false;
        const parse = createSseParser((e) => {
          if (e.event === "version") {
            try {
              onVersion((JSON.parse(e.data) as { 상태_버전: number }).상태_버전);
            } catch {
              /* 읽을 수 없는 알림은 무시한다 */
            }
          } else if (e.event === "closed") closed = true;
        });
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          parse(decoder.decode(value, { stream: true }));
          if (closed) {
            onClosed();
            return;
          }
        }
      }
    } catch {
      if (signal.aborted) return;
    }
    if (signal.aborted) return;
    await new Promise<void>((resolve) => {
      const id = setTimeout(resolve, delay);
      signal.addEventListener("abort", () => (clearTimeout(id), resolve()), { once: true });
    });
    delay = Math.min(delay * 2, 10000);
  }
}
