import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, errorMessage } from "../api/client";
import type { components } from "../api/schema";
import { clearToken, getToken, setToken } from "../api/token";

export type Account = components["schemas"]["AccountOut"];
export type ClientEnv = "PC" | "모바일";

type AuthState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "authenticated"; account: Account };

interface AuthApi {
  state: AuthState;
  /** 실패하면 사용자에게 보여 줄 메시지를 돌려주고, 성공하면 null. */
  login(id: string, password: string, autoLogin: boolean): Promise<string | null>;
  signup(id: string, password: string, nickname: string): Promise<string | null>;
  /** 아이디와 닉네임이 맞으면 새 패스워드를 정한다. 실패하면 메시지, 성공하면 null (로그인은 따로 한다). */
  resetPassword(id: string, nickname: string, newPassword: string): Promise<string | null>;
  logout(): Promise<void>;
}

const AuthContext = createContext<AuthApi | null>(null);

function detectEnv(): ClientEnv {
  return window.matchMedia?.("(pointer: coarse)").matches ? "모바일" : "PC";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  // 앱 시작 시 저장된 토큰이 아직 유효한지 서버에 확인한다.
  useEffect(() => {
    if (!getToken()) {
      setState({ status: "anonymous" });
      return;
    }
    let cancelled = false;
    api.GET("/api/auth/me").then(({ data }) => {
      if (cancelled) return;
      if (data) setState({ status: "authenticated", account: data });
      else {
        clearToken();
        setState({ status: "anonymous" });
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback<AuthApi["login"]>(async (id, password, autoLogin) => {
    const { data, error } = await api.POST("/api/auth/login", {
      body: { 아이디: id, 패스워드: password, 접속환경: detectEnv(), 자동로그인: autoLogin },
    });
    if (!data) return errorMessage(error, "로그인에 실패했습니다");
    setToken(data.토큰);
    setState({ status: "authenticated", account: data.계정 });
    return null;
  }, []);

  const signup = useCallback<AuthApi["signup"]>(
    async (id, password, nickname) => {
      const { data, error } = await api.POST("/api/auth/signup", {
        body: { 아이디: id, 패스워드: password, 닉네임: nickname },
      });
      if (!data) return errorMessage(error, "가입에 실패했습니다");
      // 가입 직후 같은 정보로 로그인한다 (자동로그인은 꺼 둔다).
      return login(id, password, false);
    },
    [login],
  );

  const resetPassword = useCallback<AuthApi["resetPassword"]>(async (id, nickname, newPassword) => {
    const { error } = await api.POST("/api/auth/reset-password", { body: { 아이디: id, 닉네임: nickname, 새_패스워드: newPassword } });
    return error ? errorMessage(error, "패스워드를 바꾸지 못했습니다") : null;
  }, []);

  const logout = useCallback(async () => {
    await api.POST("/api/auth/logout"); // 서버 폐기에 실패해도 이 기기에서는 로그아웃 처리한다.
    clearToken();
    setState({ status: "anonymous" });
  }, []);

  const value = useMemo(() => ({ state, login, signup, resetPassword, logout }), [state, login, signup, resetPassword, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthApi {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("AuthProvider 안에서만 사용할 수 있습니다");
  return ctx;
}
