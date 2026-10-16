import { useCallback, useEffect, useState } from "react";

/** 사용자가 고른 화면 모드. "system" 은 아무것도 고르지 않은 상태(기기 설정을 따름). */
export type ThemePref = "light" | "dark" | "system";

const KEY = "theme";

export function storedPref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system"; // 저장소를 못 쓰는 환경(비공개 창 등)에서도 화면은 그려야 한다
  }
}

function save(pref: ThemePref): void {
  try {
    if (pref === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, pref);
  } catch {
    /* 기억하지 못해도 이번 화면에서는 바뀐다 */
  }
}

/** html 의 data-theme 로 적용한다. system 이면 속성을 지워 CSS 가 기기 설정(prefers-color-scheme)을 따르게 한다. */
export function applyTheme(pref: ThemePref): void {
  if (pref === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = pref;
}

/**
 * 라이트/다크 둘 중 하나를 켜면 유지되고, 다른 쪽을 누르면 바뀌며, 켜진 쪽을 다시 누르면 꺼져서 기기 설정을 따른다.
 */
export function useTheme(): { pref: ThemePref; press: (which: "light" | "dark") => void } {
  const [pref, setPref] = useState<ThemePref>(storedPref);
  useEffect(() => applyTheme(pref), [pref]);
  const press = useCallback((which: "light" | "dark") => {
    const next: ThemePref = pref === which ? "system" : which;
    save(next);
    setPref(next);
  }, [pref]);
  return { pref, press };
}
