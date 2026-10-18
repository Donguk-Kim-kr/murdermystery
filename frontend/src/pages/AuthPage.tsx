import { useState, type FormEvent } from "react";

import { useAuth } from "../auth/AuthContext";
import { ThemeToggle } from "../ThemeToggle";

export function AuthPage() {
  const { login, signup } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [id, setId] = useState("");
  const [password, setPassword] = useState("");
  const [nickname, setNickname] = useState("");
  const [autoLogin, setAutoLogin] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const message = mode === "login" ? await login(id, password, autoLogin) : await signup(id, password, nickname);
    setBusy(false);
    if (message) setError(message); // 성공하면 AuthProvider 상태가 바뀌어 이 화면은 사라진다
  }

  return (
    <main className="auth">
      <div className="auth-card">
        <div className="auth-brand">
          <h1>머더미스터리</h1>
        </div>
        <form onSubmit={onSubmit}>
          {/* 탭 순서는 라이트/다크 버튼 → 아이디 → 패스워드. 버튼은 화면에서 아이디 글자 줄 오른쪽 끝에 그려진다 */}
          <ThemeToggle className="auth-theme" />
          <label>
            아이디
            <input value={id} onChange={(e) => setId(e.target.value)} autoComplete="username" required />
          </label>
          <label>
            패스워드
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              required
            />
          </label>
          {mode === "signup" && (
            <label>
              닉네임
              <input value={nickname} onChange={(e) => setNickname(e.target.value)} required />
            </label>
          )}
          {mode === "signup" && (
            <p className="field-hint">아이디는 공백 없이 50자 이하, 닉네임은 30자 이하이며 다른 참가자에게 보입니다.</p>
          )}
          {mode === "login" && (
            <label className="check">
              <input type="checkbox" checked={autoLogin} onChange={(e) => setAutoLogin(e.target.checked)} />
              자동 로그인
            </label>
          )}
          {error && <p role="alert" className="error">{error}</p>}
          <button type="submit" disabled={busy}>
            {mode === "login" ? "로그인" : "가입하기"}
          </button>
        </form>
        <p className="auth-switch">
          {mode === "login" ? "계정이 없으신가요? " : "이미 계정이 있으신가요? "}
          <button
            type="button"
            className="link"
            onClick={() => {
              setMode(mode === "login" ? "signup" : "login");
              setError(null);
            }}
          >
            {mode === "login" ? "회원가입" : "로그인으로 돌아가기"}
          </button>
        </p>
      </div>
    </main>
  );
}
