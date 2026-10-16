import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";
// 글꼴은 앱에 포함해서 기기마다 같게 보이게 한다 (Pretendard, SIL OFL 1.1). 글자 범위별 조각만 필요할 때 내려받는다.
import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import "./styles.css";
import { applyTheme, initialTheme } from "./theme";

applyTheme(initialTheme()); // 첫 화면부터 고른 테마로 그린다

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
