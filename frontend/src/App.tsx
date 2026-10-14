import { useAuth } from "./auth/AuthContext";
import { AuthPage } from "./pages/AuthPage";
import { HomePage } from "./pages/HomePage";

export function App() {
  const { state } = useAuth();
  if (state.status === "loading") return <p className="center">불러오는 중…</p>;
  if (state.status === "anonymous") return <AuthPage />;
  return <HomePage account={state.account} />;
}
