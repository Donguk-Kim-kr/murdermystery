import { useTheme } from "./theme";

const Sun = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </svg>
);
const Moon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </svg>
);

/**
 * 라이트 / 다크 버튼 한 쌍. 하나를 켜면 유지되고, 다른 쪽을 누르면 바뀌며, 켜진 쪽을 누르면 꺼져서 시스템(기기) 설정을 따른다.
 */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const { pref, press } = useTheme();
  return (
    <span className={`theme-toggle ${className}`.trim()} role="group" aria-label="화면 모드">
      <button type="button" aria-pressed={pref === "light"} aria-label="라이트 모드" title="라이트 모드" onClick={() => press("light")}>
        <Sun />
      </button>
      <button type="button" aria-pressed={pref === "dark"} aria-label="다크 모드" title="다크 모드" onClick={() => press("dark")}>
        <Moon />
      </button>
    </span>
  );
}
