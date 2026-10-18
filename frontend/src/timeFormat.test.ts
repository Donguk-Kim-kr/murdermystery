import { describe, expect, it } from "vitest";

import { composeTime, displayTime, readTime, validDay } from "./timeFormat";

describe("시간 형식", () => {
  it("고른 단위만 적고 나머지 윗단위는 2000-01-01 로 채워 저장한다", () => {
    expect(composeTime({ time: "21:30" }, "시간만")).toBe("2000-01-01T21:30");
    expect(composeTime({ day: "3", time: "21:30" }, "일까지")).toBe("2000-01-03T21:30");
    expect(composeTime({ month: "3", day: "12", time: "21:30" }, "월까지")).toBe("2000-03-12T21:30");
    expect(composeTime({ year: "2026", month: "3", day: "12", time: "21:30" }, "연도까지")).toBe("2026-03-12T21:30");
  });

  it("비었거나 없는 날짜면 빈 글이다", () => {
    expect(composeTime({ time: "" }, "시간만")).toBe("");
    expect(composeTime({ day: "", time: "10:00" }, "일까지")).toBe("");
    expect(composeTime({ month: "2", day: "30", time: "10:00" }, "월까지")).toBe("");
    expect(composeTime({ month: "2", day: "29", time: "10:00" }, "월까지")).toBe("2000-02-29T10:00");
    expect(composeTime({ year: "", month: "1", day: "1", time: "10:00" }, "연도까지")).toBe("");
    expect(validDay(13, 1)).toBe(false);
  });

  it("저장한 값을 읽고, 형식에 맞게 보여 준다", () => {
    expect(readTime("2026-03-12T21:30:00")).toEqual({ year: 2026, month: 3, day: 12, time: "21:30" });
    expect(readTime("엉뚱한 글")).toBeNull();
    const v = "2026-03-12T21:30:00";
    expect(displayTime(v, "시간만")).toBe("21:30");
    expect(displayTime(v, "일까지")).toBe("12일 21:30");
    expect(displayTime(v, "월까지")).toBe("3월 12일 21:30");
    expect(displayTime(v, "연도까지")).toBe("2026년 3월 12일 21:30");
  });
});
