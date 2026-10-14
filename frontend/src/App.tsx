import { Route, Routes } from "react-router-dom";

import { useAuth } from "./auth/AuthContext";
import { Layout } from "./Layout";
import { AuthPage } from "./pages/AuthPage";
import { WorkNewPage } from "./pages/WorkNewPage";
import { WorkPage } from "./pages/WorkPage";
import { WorksListPage } from "./pages/WorksListPage";

export function App() {
  const { state } = useAuth();
  if (state.status === "loading") return <p className="center">불러오는 중…</p>;
  if (state.status === "anonymous") return <AuthPage />;
  return (
    <Routes>
      <Route element={<Layout account={state.account} />}>
        <Route path="/" element={<WorksListPage />} />
        <Route path="/works/new" element={<WorkNewPage />} />
        <Route path="/works/:id" element={<WorkPage />} />
        <Route path="*" element={<main className="page"><p>페이지를 찾을 수 없습니다.</p></main>} />
      </Route>
    </Routes>
  );
}
