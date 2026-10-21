/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // 개발 중에는 /api 요청을 FastAPI(8000)로 넘긴다. 같은 출처가 되므로 CORS 설정이 필요 없다.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    // 간헐적으로(전체 시험을 여러 번 돌리면 8번 중 1번쯤) 시험이 끝난 뒤 늦게 도착한 요청이 가짜 fetch 가 풀린 뒤의 진짜 fetch 로 나가
    // "fetch failed / ECONNREFUSED 127.0.0.1:3000" 이 처리되지 않은 오류로 잡히고 시험이 모두 통과해도 종료 코드가 1 이 된다.
    // 시험 결과와 무관한 이 오류 하나만 걸러서 자동 시험(GitHub Actions)이 이유 없이 빨개지지 않게 한다. 다른 처리되지 않은 오류는 그대로 실패로 센다.
    onUnhandledError(error) {
      // localhost 가 ::1 과 127.0.0.1 둘로 풀리는 환경(GitHub Actions)에서는 원인이 AggregateError 로 한 겹 더 감싸여 온다.
      type NetError = { message?: string; code?: string; errors?: NetError[] };
      const e = error as { message?: string; cause?: NetError };
      const parts = [e.cause?.message, e.cause?.code, ...(e.cause?.errors ?? []).flatMap((x) => [x.message, x.code])];
      if ((e.message ?? "").includes("fetch failed") && parts.some((p) => p?.includes("ECONNREFUSED"))) return false;
    },
  },
});
