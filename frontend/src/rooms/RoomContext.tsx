import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api } from "../api/client";
import type { components } from "../api/schema";

export type Room = components["schemas"]["RoomOut"];

/** 대기실 상태를 몇 초마다 서버에서 읽는다. 이 호출이 서버에는 "아직 접속 중"이라는 신호(하트비트)이기도 하다. */
const POLL_MS = import.meta.env.MODE === "test" ? 60 : 3000;

interface RoomApi {
  /** undefined: 아직 모름, null: 참여 중인 방 없음 */
  room: Room | null | undefined;
  refresh(): Promise<void>;
}

const RoomContext = createContext<RoomApi | null>(null);

export function RoomProvider({ children }: { children: ReactNode }) {
  const [room, setRoom] = useState<Room | null | undefined>(undefined);

  const refresh = useCallback(async () => {
    const { data, error } = await api.GET("/api/rooms/me");
    if (!error) setRoom(data ?? null);
  }, []);

  useEffect(() => {
    void refresh();
    // 다른 창(예: Discord)으로 옮겨 탭이 숨겨져도 계속 부른다. 브라우저가 늦추더라도 서버의 끊김 판단 시간이 이를 감안한다.
    const id = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const value = useMemo(() => ({ room, refresh }), [room, refresh]);
  return <RoomContext.Provider value={value}>{children}</RoomContext.Provider>;
}

export function useRoom(): RoomApi {
  const ctx = useContext(RoomContext);
  if (!ctx) throw new Error("RoomProvider 안에서만 사용할 수 있습니다");
  return ctx;
}
