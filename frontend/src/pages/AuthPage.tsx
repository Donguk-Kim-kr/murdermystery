import { useState, type FormEvent } from "react";

import { useAuth } from "../auth/AuthContext";

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
    <main className="card">
      <h1>머더미스터리</h1>
      <h2>{mode === "login" ? "로그인" : "회원가입"}</h2>
      <form onSubmit={onSubmit}>
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
    </main>
  );
}
