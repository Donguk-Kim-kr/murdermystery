import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "./schema";
import { getToken } from "./token";
import { josa } from "../josa";

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

interface ValidationItem {
  type?: string;
  loc?: unknown[];
  ctx?: { min_length?: number; max_length?: number; pattern?: string; ge?: number; le?: number };
}

/** 검증 오류 한 건을 "어느 항목이 왜 안 되는지" 알려 주는 문장으로 바꾼다. 항목 이름은 서버의 필드 이름(한글)이다. */
function validationSentence(item: ValidationItem): string {
  const field = [...(item.loc ?? [])].reverse().find((v): v is string => typeof v === "string" && v !== "body");
  const name = field ?? "입력값";
  const ctx = item.ctx ?? {};
  switch (item.type) {
    case "missing":
      return `${josa(name, "을/를")} 입력해 주세요`;
    case "string_too_short":
      return ctx.min_length === 1 ? `${josa(name, "을/를")} 입력해 주세요` : `${josa(name, "은/는")} ${ctx.min_length}자 이상이어야 합니다`;
    case "string_too_long":
      return `${josa(name, "은/는")} ${ctx.max_length}자 이하여야 합니다`;
    case "string_pattern_mismatch":
      return ctx.pattern === "^\\S+$" ? `${josa(name, "은/는")} 공백 없이 입력해 주세요` : `${name}에 쓸 수 없는 글자가 있습니다`;
    case "greater_than_equal":
      return `${josa(name, "은/는")} ${ctx.ge} 이상이어야 합니다`;
    case "less_than_equal":
      return `${josa(name, "은/는")} ${ctx.le} 이하여야 합니다`;
    default:
      return `${name} 값을 확인해 주세요`;
  }
}

/** FastAPI 오류 응답({detail: 문자열 | 검증오류 배열})에서 사용자에게 보여 줄 문장을 꺼낸다. 검증 오류는 어느 항목이 왜 안 되는지 알려 준다. */
export function errorMessage(error: unknown, fallback = "요청에 실패했습니다"): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const sentences = [...new Set((detail as ValidationItem[]).map(validationSentence))];
    return sentences.length > 0 ? sentences.slice(0, 3).join(" · ") : "입력값을 확인해 주세요";
  }
  return fallback;
}

export interface HttpResult<T> {
  data?: T;
  error?: unknown;
  status: number;
}

/**
 * 스키마 타입이 없는 범용 호출 (작업공간 콘텐츠·라이브러리·확정 API).
 * 응답이 2xx 이면 `data`(본문이 없으면 undefined), 아니면 `error`(FastAPI 오류 본문)를 돌려준다.
 */
export async function http<T = unknown>(method: string, path: string, body?: unknown): Promise<HttpResult<T>> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (body !== undefined) headers.set("Content-Type", "application/json");
  const res = await fetch(
    new Request(new URL(path, window.location.origin), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
  const text = await res.text();
  const parsed = text ? (JSON.parse(text) as unknown) : undefined;
  return res.ok ? { data: parsed as T, status: res.status } : { error: parsed ?? {}, status: res.status };
}
