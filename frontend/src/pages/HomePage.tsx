import { useAuth, type Account } from "../auth/AuthContext";

export function HomePage({ account }: { account: Account }) {
  const { logout } = useAuth();
  return (
    <main className="card">
      <h1>머더미스터리</h1>
      <p>
        <strong>{account.닉네임}</strong>님, 환영합니다.
      </p>
      <button type="button" onClick={() => void logout()}>
        로그아웃
      </button>
    </main>
  );
}
