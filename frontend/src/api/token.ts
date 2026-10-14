// 세션 토큰 보관. 저장소 접근이 막힌 환경(사생활 보호 모드 등)에서도 앱이 죽지 않도록 모두 try/catch 한다.
const KEY = "mm.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(KEY, token);
  } catch {
    /* 저장 실패 시 새로고침하면 로그아웃된다 */
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* 무시 */
  }
}
