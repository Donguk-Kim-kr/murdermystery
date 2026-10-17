import { useCallback, useEffect, useRef, useState } from "react";

import { api, errorMessage } from "../api/client";
import type { components } from "../api/schema";
import { connectEvents } from "./sse";

export type GameState = components["schemas"]["GameStateOut"];

export interface GameApi {
  /** undefined: 아직 모름 */
  state: GameState | undefined;
  /** 게임이 없다(끝나서 정리되었거나 참여하지 않음) */
  missing: boolean;
  /** 마지막 행동의 오류 문장. 다음 행동을 하면 지워진다 */
  error: string | null;
  answer(questionId: string, value: unknown): Promise<boolean>;
  advance(): Promise<boolean>;
  pause(paused: boolean): Promise<boolean>;
  setAutoAdvance(on: boolean): Promise<boolean>;
  giveAuthority(account: number): Promise<boolean>;
}

/**
 * 내 게임의 상태를 읽고 실시간 알림을 받는다.
 * 상태 버전은 늘기만 하므로, 늦게 도착한 오래된 응답은 버린다(알림과 행동 응답이 엇갈려도 화면이 뒤로 가지 않는다).
 */
export function useGame(): GameApi {
  const [state, setState] = useState<GameState | undefined>(undefined);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const version = useRef(-1);
  const alive = useRef(true);

  const apply = useCallback((next: GameState) => {
    if (!alive.current || next.상태_버전 < version.current) return;
    version.current = next.상태_버전;
    setState(next);
    setMissing(false);
  }, []);

  const load = useCallback(async () => {
    const { data, response } = await api.GET("/api/game/me/state");
    if (!alive.current) return;
    if (data) apply(data);
    else if (response.status === 404) setMissing(true);
  }, [apply]);

  useEffect(() => {
    alive.current = true;
    void load();
    const controller = new AbortController();
    void connectEvents({
      signal: controller.signal,
      onVersion: (v) => {
        if (v > version.current) void load();
      },
      onClosed: () => setMissing(true),
    });
    // 탭이 숨겨졌다가 돌아오거나 네트워크가 돌아오면 알림을 놓쳤을 수 있으니 한 번 더 읽는다.
    const refresh = () => {
      if (document.visibilityState !== "hidden") void load();
    };
    document.addEventListener("visibilitychange", refresh);
    window.addEventListener("online", refresh);
    return () => {
      alive.current = false;
      controller.abort();
      document.removeEventListener("visibilitychange", refresh);
      window.removeEventListener("online", refresh);
    };
  }, [load]);

  const act = useCallback(
    async (run: () => Promise<{ data?: GameState; error?: unknown }>, fallback: string) => {
      setError(null);
      const { data, error: err } = await run();
      if (data) apply(data);
      if (err) {
        setError(errorMessage(err, fallback));
        // 거부당했다면 내가 본 화면이 낡았을 수 있다
        void load();
        return false;
      }
      return true;
    },
    [apply, load],
  );

  return {
    state,
    missing,
    error,
    answer: (questionId, value) =>
      act(() => api.POST("/api/game/me/answer", { body: { 질문ID: questionId, 값: value } }), "답을 보내지 못했습니다"),
    advance: () => act(() => api.POST("/api/game/me/advance"), "다음 단계로 넘어가지 못했습니다"),
    pause: (paused) => act(() => api.POST("/api/game/me/pause", { body: { 일시정지: paused } }), "시간을 바꾸지 못했습니다"),
    setAutoAdvance: (on) => act(() => api.POST("/api/game/me/settings", { body: { 자동_진행: on } }), "설정을 바꾸지 못했습니다"),
    giveAuthority: (account) =>
      act(() => api.POST("/api/game/me/authority", { body: { 계정_번호: account } }), "진행 권한을 맡기지 못했습니다"),
  };
}
