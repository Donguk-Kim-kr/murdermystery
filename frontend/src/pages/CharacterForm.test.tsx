import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CharacterForm, type Character } from "./CharacterForm";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

let sent: { method: string; path: string; body: Record<string, unknown> }[];

beforeEach(() => {
  sent = [];
  vi.stubGlobal("fetch", async (input: Request) => {
    sent.push({ method: input.method, path: new URL(input.url).pathname, body: JSON.parse((await input.clone().text()) || "{}") });
    return json({}, 201);
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const saved = (parts: { ID: string | null; 본문: string }[]) =>
  ({ 순서: 1, 이름: "의사", 서사: "", 서사_부분: parts, 범인: false, NPC: false }) as unknown as Character;

const renderForm = (character?: Character) =>
  render(<CharacterForm workId={7} character={character} onSaved={() => undefined} onCancel={() => undefined} />);

describe("서사 입력", () => {
  it("처음에는 서사 1 하나이고 10000자까지 쓸 수 있다고 알린다", () => {
    renderForm();
    expect(screen.getByText("0/10000자")).toBeInTheDocument();
    expect(screen.getByText(/서사를 2개로 나누면 각 서사는 5000자까지/)).toBeInTheDocument();
  });

  it("서사 추가하기를 누르면 새 서사가 생기고 제한이 줄어든다", async () => {
    renderForm();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "서사 추가하기" }));
    expect(screen.getAllByText("0/5000자")).toHaveLength(2);
    expect(screen.getByText("서사 2")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "서사 추가하기" }));
    expect(screen.getAllByText("0/3333자")).toHaveLength(3);
  });

  it("5개까지만 나눌 수 있다", async () => {
    renderForm();
    const user = userEvent.setup();
    for (let i = 0; i < 4; i++) await user.click(screen.getByRole("button", { name: "서사 추가하기" }));
    expect(screen.getAllByText("0/2000자")).toHaveLength(5);
    expect(screen.getByRole("button", { name: "서사 추가하기" })).toBeDisabled();
  });

  it("추가하면 기존 서사가 새 제한을 넘을 때 미리 알리고, 취소하면 추가하지 않는다", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderForm(saved([{ ID: "abc123", 본문: "가".repeat(6000) }]));
    expect(screen.getByText(/지금 서사 1이\(가\) 넘습니다/)).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "서사 추가하기" }));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("각 서사는 5000자까지"));
    expect(screen.queryByText("서사 2")).toBeNull();
    confirm.mockReturnValue(true);
    await user.click(screen.getByRole("button", { name: "서사 추가하기" }));
    expect(screen.getByText("서사 2")).toBeInTheDocument();
    expect(screen.getByText("6000/5000자")).toHaveClass("error");
  });

  it("저장할 때 기존 서사의 ID 를 그대로 보내고 새 서사는 ID 없이 보낸다", async () => {
    renderForm(saved([{ ID: "abc123", 본문: "첫째" }]));
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "서사 추가하기" }));
    await user.type(screen.getAllByRole("textbox").at(-1)!, "둘째");
    await user.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0].method).toBe("PATCH");
    expect(sent[0].body.서사_부분).toEqual([
      { ID: "abc123", 본문: "첫째" },
      { ID: null, 본문: "둘째" },
    ]);
    expect(sent[0].body).not.toHaveProperty("서사");
  });

  it("서사를 하나도 쓰지 않으면 빈 목록으로 저장한다", async () => {
    renderForm();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/이름/), "의사");
    await user.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0].method).toBe("POST");
    expect(sent[0].body.서사_부분).toEqual([]);
  });

  it("서사를 삭제할 수 있고 하나만 남으면 삭제 버튼이 없다", async () => {
    renderForm(saved([{ ID: "a00001", 본문: "하나" }, { ID: "b00002", 본문: "둘" }]));
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "서사 1 삭제" }));
    expect(screen.queryByRole("button", { name: /삭제/ })).toBeNull();
    expect(screen.getByDisplayValue("둘")).toBeInTheDocument();
    expect(screen.getByText("1/10000자")).toBeInTheDocument();
  });
});
