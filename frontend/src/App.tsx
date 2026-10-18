import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth/AuthContext";
import { ConfirmProvider } from "./confirm/ConfirmContext";
import { Layout } from "./Layout";
import { AuthPage } from "./pages/AuthPage";
import { CreateRoomPage } from "./pages/CreateRoomPage";
import { LibraryPage } from "./pages/LibraryPage";
import { JoinByLinkPage, JoinRoomPage } from "./pages/JoinRoomPage";
import { MakeHubPage } from "./pages/MakeHubPage";
import { PlayHomePage } from "./pages/PlayHomePage";
import { RecordsPage } from "./pages/RecordsPage";
import { RoomPage } from "./pages/RoomPage";
import { WorkPage } from "./pages/WorkPage";
import { WorksListPage } from "./pages/WorksListPage";

/** 화면 전체를 감싸 어디서든 `useConfirm()` 으로 확인 팝업을 쓸 수 있게 한다. */
export function App() {
  return (
    <ConfirmProvider>
      <AppRoutes />
    </ConfirmProvider>
  );
}

function AppRoutes() {
  const { state } = useAuth();
  if (state.status === "loading") return <p className="center">불러오는 중…</p>;
  if (state.status === "anonymous") return <AuthPage />;
  return (
    <Routes>
      <Route element={<Layout account={state.account} />}>
        <Route path="/" element={<PlayHomePage />} />
        <Route path="/make" element={<MakeHubPage />} />
        <Route path="/make/games" element={<WorksListPage />} />
        <Route path="/make/library" element={<LibraryPage />} />
        <Route path="/records" element={<RecordsPage />} />
        <Route path="/works/:id" element={<WorkPage />} />
        <Route path="/library" element={<Navigate to="/make/library" replace />} />
        <Route path="/rooms/join" element={<JoinRoomPage />} />
        <Route path="/join/:code" element={<JoinByLinkPage />} />
        <Route path="/rooms/new/:workId" element={<CreateRoomPage />} />
        <Route path="/room" element={<RoomPage />} />
        <Route path="*" element={<main className="page"><p>페이지를 찾을 수 없습니다.</p></main>} />
      </Route>
    </Routes>
  );
}
