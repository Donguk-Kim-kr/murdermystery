import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "./schema";
import { getToken } from "./token";

const authMiddleware: Middleware = {
  onRequest({ request }) {
    const token = getToken();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
};

// 같은 출처로 요청한다. 개발 중에는 Vite 프록시가 /api 를 백엔드로 넘긴다.
// (Request 는 상대 경로를 받지 못하는 환경이 있어 현재 출처를 명시한다.)
// fetch 는 호출 시점에 전역에서 읽는다 (테스트에서 교체할 수 있도록).
export const api = createClient<paths>({ baseUrl: window.location.origin, fetch: (req) => fetch(req) });
api.use(authMiddleware);

/** FastAPI 오류 응답({detail: 문자열 | 검증오류 배열})에서 사용자에게 보여 줄 문장을 꺼낸다. */
export function errorMessage(error: unknown, fallback = "요청에 실패했습니다"): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return "입력값을 확인해 주세요";
  return fallback;
}
