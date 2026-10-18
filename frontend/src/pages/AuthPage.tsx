import { useState, type FormEvent } from "react";

import { useAuth } from "../auth/AuthContext";
import { ThemeToggle } from "../ThemeToggle";

export function AuthPage() {
  const { login, signup, resetPassword } = useAuth();
  const [mode, setMode] = useState<"login" | "signup" | "reset">("login");
  const [notice, setNotice] = useState<string | null>(null);
  const [id, setId] = useState("");
  const [password, setPassword] = useState("");
  const [nickname, setNickname] = useState("");
  const [autoLogin, setAutoLogin] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  /** 로그인·회원가입·패스워드 찾기 화면을 오갈 때는 입력한 내용과 안내를 모두 비운다. */
  function switchTo(next: "login" | "signup" | "reset") {
    setMode(next);
    setId("");
    setPassword("");
    setNickname("");
    setAutoLogin(false);
    setError(null);
    setNotice(null);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    if (mode === "reset") {
      const message = await resetPassword(id, nickname, password);
      setBusy(false);
      if (message) setError(message);
      else {
        // 바꾼 뒤에는 로그인 화면으로 돌아간다(아이디는 남기고 새 패스워드는 다시 입력하게 한다)
        setPassword("");
        setNickname("");
        setNotice("패스워드를 바꿨습니다. 새 패스워드로 로그인해 주세요.");
        setMode("login");
      }
      return;
    }
    setNotice(null);
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
            {mode === "reset" ? "새 패스워드" : "패스워드"}
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              required
            />
          </label>
          {mode !== "login" && (
            <label>
              닉네임
              <input value={nickname} onChange={(e) => setNickname(e.target.value)} required />
            </label>
          )}
          {mode === "reset" && (
            <p className="field-hint">가입할 때 쓴 아이디와 닉네임이 둘 다 맞으면 새 패스워드를 정할 수 있습니다. 바꾸면 이미 로그인해 둔 기기는 모두 로그아웃됩니다.</p>
          )}
          {mode === "login" && (
            <label className="check">
              <input type="checkbox" checked={autoLogin} onChange={(e) => setAutoLogin(e.target.checked)} />
              자동 로그인
            </label>
          )}
          {notice && mode === "login" && <p role="status" className="notice-ok">{notice}</p>}
          {error && <p role="alert" className="error">{error}</p>}
          <button type="submit" disabled={busy}>
            {mode === "login" ? "로그인" : mode === "signup" ? "가입하기" : "패스워드 바꾸기"}
          </button>
        </form>
        <p className="auth-switch">
          {mode === "login" ? "계정이 없으신가요? " : "이미 계정이 있으신가요? "}
          <button
            type="button"
            className="link"
            onClick={() => switchTo(mode === "login" ? "signup" : "login")}
          >
            {mode === "login" ? "회원가입" : "로그인으로 돌아가기"}
          </button>
        </p>
        {mode === "login" && (
          <p className="auth-switch">
            <button type="button" className="link" onClick={() => switchTo("reset")}>
              패스워드를 잊으셨나요?
            </button>
          </p>
        )}
      </div>
    </main>
  );
}
