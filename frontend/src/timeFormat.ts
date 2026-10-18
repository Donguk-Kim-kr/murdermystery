/**
 * 타임라인 같은 시간 칸을 어디까지 적을지(작품마다 고른다). 값은 항상 `YYYY-MM-DDTHH:MM` 한 가지 모양으로 저장하고,
 * 적지 않는 윗단위(연·월·일)는 2000-01-01 로 채운다. 그래서 형식을 바꿔도 이미 적은 값은 그대로 남는다.
 */
export const TIME_FORMATS = ["시간만", "일까지", "월까지", "연도까지"] as const;
export type TimeFormat = (typeof TIME_FORMATS)[number];

export const isTimeFormat = (v: unknown): v is TimeFormat => TIME_FORMATS.includes(v as TimeFormat);

/** 저장한 값에서 연·월·일·시·분을 읽는다. 읽을 수 없으면 null. */
export function readTime(value: unknown): { year: number; month: number; day: number; time: string } | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(String(value ?? ""));
  if (!m) return null;
  return { year: Number(m[1]), month: Number(m[2]), day: Number(m[3]), time: `${m[4]}:${m[5]}` };
}

const pad = (n: number, width = 2) => String(n).padStart(width, "0");

/** 월·일이 실제로 있는 날인지(2월 30일 같은 것은 없다). 연도는 윤년인 2000 으로 본다. */
export function validDay(month: number, day: number, year = 2000): boolean {
  if (!Number.isInteger(month) || !Number.isInteger(day) || month < 1 || month > 12 || day < 1) return false;
  return day <= new Date(year, month, 0).getDate();
}

/** 고른 단위만큼의 값을 저장하는 모양으로 합친다. 비었거나 맞지 않으면 빈 글. */
export function composeTime(parts: { year?: string; month?: string; day?: string; time: string }, format: TimeFormat): string {
  if (!/^\d{2}:\d{2}$/.test(parts.time)) return "";
  const year = format === "연도까지" ? Number(parts.year) : 2000;
  const month = format === "월까지" || format === "연도까지" ? Number(parts.month) : 1;
  const day = format === "시간만" ? 1 : Number(parts.day);
  if (format === "연도까지" && !(Number.isInteger(year) && year >= 1 && year <= 9999)) return "";
  if (!validDay(month, day, year)) return "";
  return `${pad(year, 4)}-${pad(month)}-${pad(day)}T${parts.time}`;
}

/** 목록 같은 곳에 보여 줄 글: 시간만 "21:30", 일까지 "3일 21:30", 월까지 "3월 12일 21:30", 연도까지 "2026년 3월 12일 21:30". */
export function displayTime(value: unknown, format: TimeFormat): string {
  const t = readTime(value);
  if (!t) return String(value ?? "");
  if (format === "시간만") return t.time;
  if (format === "일까지") return `${t.day}일 ${t.time}`;
  if (format === "월까지") return `${t.month}월 ${t.day}일 ${t.time}`;
  return `${t.year}년 ${t.month}월 ${t.day}일 ${t.time}`;
}
