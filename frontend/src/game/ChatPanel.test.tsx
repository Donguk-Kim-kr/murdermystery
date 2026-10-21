import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPanel } from "./ChatPanel";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

const person = (n: number, name: string, character: string | null = null) => ({ 계정_번호: n, 닉네임: name, 인물_이름: character });
const msg = (n: number, place: string, from: ReturnType<typeof person>, text: string) => ({ 번호: n, 장소: place, 보낸이: from, 내용: text, 보낸일시: "2026-10-18T12:00:00Z" });

let view: Record<string, unknown>;
let sent: { path: string; body: Record<string, unknown> }[];
let failNext: string | null;

beforeEach(() => {
  sent = [];
  failNext = null;
  vi.stubGlobal("fetch", async (input: Request) => {
    const url = new URL(input.url);
    if (input.method === "GET") {
      const after = Number(url.searchParams.get("after") ?? 0);
      const all = view.메시지 as { 번호: number }[];
      return json({ ...view, 메시지: all.filter((m) => m.번호 > after) });
    }
    sent.push({ path: url.pathname, body: JSON.parse(await input.clone().text()) });
    if (failNext) return json({ detail: failNext }, 409);
    return json(view);
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const seo = person(1, "서윤", "서윤");
const ji = person(2, "지우");
const rooms = (a: ReturnType<typeof person>[] = [], b: ReturnType<typeof person>[] = []) => [
  { 이름: "전체", 최대인원: null, 사람들: [seo, ji] },
  { 이름: "밀담 A", 최대인원: 2, 사람들: a },
  { 이름: "밀담 B", 최대인원: 2, 사람들: b },
];

describe("게임 채팅", () => {
  it("플레이어는 자기 장소의 대화를 보고 메시지를 보낸다", async () => {
    view = { 내_위치: "전체", 역할: "플레이어", 장소들: rooms(), 메시지: [msg(1, "전체", ji, "안녕하세요")] };
    render(<ChatPanel />);
    const log = await screen.findByRole("list", { name: "전체 대화" });
    expect(await within(log).findByText("안녕하세요")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /밀담 A.*비어 있음/ })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("메시지"), "반갑습니다");
    await userEvent.click(screen.getByRole("button", { name: "보내기" }));
    await waitFor(() => expect(sent).toEqual([{ path: "/api/game/me/chat/send", body: { 내용: "반갑습니다" } }]));
    expect(screen.getByLabelText("메시지")).toHaveValue("");
  });

  it("장소를 누르면 그곳으로 옮기고, 가득 찬 밀담 장소는 들어갈 수 없다", async () => {
    view = { 내_위치: "전체", 역할: "플레이어", 장소들: rooms([person(3, "민재"), person(4, "도현")]), 메시지: [] };
    render(<ChatPanel />);
    const full = await screen.findByRole("button", { name: /밀담 A.*민재, 도현/ });
    expect(full).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /밀담 B/ }));
    await waitFor(() => expect(sent).toEqual([{ path: "/api/game/me/chat/move", body: { 장소: "밀담 B" } }]));
  });

  it("옮기지 못하면 안내가 보인다", async () => {
    view = { 내_위치: "전체", 역할: "플레이어", 장소들: rooms(), 메시지: [] };
    render(<ChatPanel />);
    failNext = "밀담 A은 이미 두 사람이 있습니다";
    await userEvent.click(await screen.findByRole("button", { name: /밀담 A/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("이미 두 사람이");
  });

  it("일반 관전자는 전체 대화만 읽고 쓰지 못한다", async () => {
    view = { 내_위치: null, 역할: "일반 관전", 장소들: rooms([person(3, "민재")]), 메시지: [msg(1, "전체", ji, "공개 말")] };
    render(<ChatPanel />);
    expect(await within(await screen.findByRole("list", { name: "전체 대화" })).findByText("공개 말")).toBeInTheDocument();
    expect(screen.queryByLabelText("메시지")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /밀담 A/ })).toBeDisabled();
    expect(screen.queryByText("관전자는 전체 대화를 볼 수만 있습니다.")).not.toBeInTheDocument();          // 안내 글은 두지 않는다
  });

  it("GM 관전자는 밀담 장소를 골라 그 대화를 읽는다", async () => {
    view = {
      내_위치: null, 역할: "GM 관전", 장소들: rooms([seo, ji]),
      메시지: [msg(1, "전체", ji, "공개 말"), msg(2, "밀담 A", seo, "속닥속닥")],
    };
    render(<ChatPanel />);
    await within(await screen.findByRole("list", { name: "전체 대화" })).findByText("공개 말");
    await userEvent.click(screen.getByRole("button", { name: /밀담 A/ }));
    const secret = await screen.findByRole("list", { name: "밀담 A 대화" });
    expect(within(secret).getByText("속닥속닥")).toBeInTheDocument();
    expect(within(secret).queryByText("공개 말")).not.toBeInTheDocument();
    expect(sent).toEqual([]);                                                       // 옮기는 것이 아니라 보기만 한다
  });

  it("크게 보기를 누르면 큰 창이 되고, 작게나 Esc 로 돌아온다", async () => {
    view = { 내_위치: "전체", 역할: "플레이어", 장소들: rooms(), 메시지: [msg(1, "전체", ji, "안녕하세요")] };
    render(<ChatPanel />);
    await screen.findByRole("button", { name: "크게 보기" });                          // 불러온 뒤의 화면
    const panel = screen.getByRole("region", { name: "채팅" });
    expect(panel).not.toHaveClass("big");
    await userEvent.click(within(panel).getByRole("button", { name: "크게 보기" }));
    expect(panel).toHaveClass("big");
    await userEvent.click(within(panel).getByRole("button", { name: "작게" }));
    expect(panel).not.toHaveClass("big");
    await userEvent.click(within(panel).getByRole("button", { name: "크게 보기" }));
    await userEvent.keyboard("{Escape}");
    expect(panel).not.toHaveClass("big");
  });

  it("대화에는 닉네임이 아니라 캐릭터 이름이 보이고, 사람마다 글자 색이 다르다", async () => {
    const a = person(11, "AI 1", "오태훈");
    const b = person(12, "AI 2", "황칠성");
    view = {
      내_위치: "전체", 역할: "플레이어",
      장소들: [{ 이름: "전체", 최대인원: null, 사람들: [a, b] }, { 이름: "밀담 A", 최대인원: 2, 사람들: [] }],
      메시지: [msg(1, "전체", { ...a, 인물_이름: null }, "확인했습니다."), msg(2, "전체", b, "뭘 보냐?")],
    };
    render(<ChatPanel />);
    const log = await screen.findByRole("list", { name: "전체 대화" });
    const first = (await within(log).findByText("확인했습니다.")).closest("li")!;
    const second = within(log).getByText("뭘 보냐?").closest("li")!;
    expect(within(first).getByText("오태훈")).toBeInTheDocument();                       // 받아 올 때 이름이 없었어도 지금의 캐릭터 이름으로 보인다
    expect(within(second).getByText("황칠성")).toBeInTheDocument();
    expect(screen.queryByText("AI 1")).not.toBeInTheDocument();
    const color = (li: HTMLElement) => [...li.classList].find((c) => /^chat-c\d$/.test(c));
    expect(color(first)).toBeDefined();
    expect(color(first)).not.toEqual(color(second));
    const places = screen.getByRole("list", { name: "채팅 장소" });
    expect(within(places).getByText("오태훈")).toHaveClass(color(first)!);               // 장소의 이름도 같은 색
  });
});
