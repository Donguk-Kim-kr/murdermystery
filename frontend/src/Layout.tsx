import { Link, Outlet } from "react-router-dom";

import type { Account } from "./auth/AuthContext";
import { useAuth } from "./auth/AuthContext";

/** 앱 로고 마크 (돋보기). 외부 이미지 없이 SVG 로 그린다. */
export function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg width="62%" height="62%" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m20 20-4.8-4.8" />
      </svg>
    </span>
  );
}

export function Layout({ account }: { account: Account }) {
  const { logout } = useAuth();
  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">
          <BrandMark />
          머더미스터리
        </Link>
        <span className="who">
          <span className="avatar" aria-hidden="true">{account.닉네임.slice(0, 1)}</span>
          <span className="who-name">{account.닉네임}</span>
        </span>
        <button type="button" className="small secondary" onClick={() => void logout()}>
          로그아웃
        </button>
      </header>
      <Outlet />
    </>
  );
}
