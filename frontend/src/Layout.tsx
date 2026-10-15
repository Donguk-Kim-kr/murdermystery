import { Link, Outlet } from "react-router-dom";

import type { Account } from "./auth/AuthContext";
import { useAuth } from "./auth/AuthContext";
import { RoomProvider, useRoom } from "./rooms/RoomContext";

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

function RoomChip() {
  const { room } = useRoom();
  if (!room) return null;
  return (
    <Link to="/room" className="chip accent room-chip" aria-label="내 방">
      방 {room.입장코드}
    </Link>
  );
}

export function Layout({ account }: { account: Account }) {
  const { logout } = useAuth();
  return (
    <RoomProvider>
      <header className="topbar">
        <Link to="/" className="brand">
          <BrandMark />
          머더미스터리
        </Link>
        <RoomChip />
        <span className="who">{account.닉네임}</span>
        <button type="button" className="small secondary" onClick={() => void logout()}>
          로그아웃
        </button>
      </header>
      <Outlet />
    </RoomProvider>
  );
}
