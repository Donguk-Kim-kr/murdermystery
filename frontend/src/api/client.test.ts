import { describe, expect, it } from "vitest";

import { errorMessage } from "./client";

const item = (type: string, field: string, ctx: Record<string, unknown> = {}) => ({ type, loc: ["body", field], msg: "x", input: "", ctx });

describe("errorMessage", () => {
  it("문자열 오류는 그대로 보여 준다", () => {
    expect(errorMessage({ detail: "이미 사용 중인 아이디입니다" })).toBe("이미 사용 중인 아이디입니다");
  });

  it("검증 오류는 어느 항목이 왜 안 되는지 알려 준다", () => {
    expect(errorMessage({ detail: [item("string_too_short", "패스워드", { min_length: 8 })] })).toBe("패스워드는 8자 이상이어야 합니다");
    expect(errorMessage({ detail: [item("string_too_long", "닉네임", { max_length: 30 })] })).toBe("닉네임은 30자 이하여야 합니다");
    expect(errorMessage({ detail: [item("string_pattern_mismatch", "아이디", { pattern: "^\\S+$" })] })).toBe("아이디는 공백 없이 입력해 주세요");
    expect(errorMessage({ detail: [item("string_too_short", "아이디", { min_length: 1 })] })).toBe("아이디를 입력해 주세요");
    expect(errorMessage({ detail: [item("missing", "닉네임")] })).toBe("닉네임을 입력해 주세요");
  });

  it("여러 항목이 틀리면 함께 알려 주고 같은 문장은 한 번만 보여 준다", () => {
    const detail = [
      item("string_pattern_mismatch", "아이디", { pattern: "^\\S+$" }),
      item("string_too_short", "패스워드", { min_length: 8 }),
      item("string_too_short", "패스워드", { min_length: 8 }),
    ];
    expect(errorMessage({ detail })).toBe("아이디는 공백 없이 입력해 주세요 · 패스워드는 8자 이상이어야 합니다");
  });

  it("알 수 없는 오류는 항목 이름과 함께 값을 확인하라고 한다", () => {
    expect(errorMessage({ detail: [item("something_else", "나이")] })).toBe("나이 값을 확인해 주세요");
    expect(errorMessage({ detail: [] })).toBe("입력값을 확인해 주세요");
    expect(errorMessage({}, "실패")).toBe("실패");
  });
});
