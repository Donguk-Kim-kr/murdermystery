import { Link, Outlet } from "react-router-dom";

import type { Account } from "./auth/AuthContext";
import { useAuth } from "./auth/AuthContext";

export function Layout({ account }: { account: Account }) {
  const { logout } = useAuth();
  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">머더미스터리</Link>
        <span className="who">{account.닉네임}</span>
        <button type="button" className="small" onClick={() => void logout()}>
          로그아웃
        </button>
      </header>
      <Outlet />
    </>
  );
}
