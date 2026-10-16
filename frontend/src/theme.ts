import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const KEY = "theme";

function stored(): Theme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null; // 저장소를 못 쓰는 환경(비공개 창 등)에서도 화면은 그려야 한다
  }
}

function system(): Theme {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

/** 화면에 적용할 테마: 사용자가 고른 값이 있으면 그것, 없으면 기기 설정. */
export function initialTheme(): Theme {
  return stored() ?? system();
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
}

/** 다크 모드 켜고 끄기. 고른 값은 이 브라우저에 기억한다. */
export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(() =>
    (document.documentElement.dataset.theme as Theme | undefined) ?? initialTheme(),
  );
  useEffect(() => applyTheme(theme), [theme]);
  const toggle = useCallback(() => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* 기억하지 못해도 이번 화면에서는 바뀐다 */
    }
    setTheme(next);
  }, [theme]);
  return { theme, toggle };
}
