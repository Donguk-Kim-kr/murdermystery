import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";

type Handler = (req: Request) => Response | Promise<Response>;
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

let routes: Record<string, Handler>;
const calls: { key: string; req: Request }[] = [];

beforeEach(() => {
  routes = {};
  calls.length = 0;
  localStorage.clear();
  vi.stubGlobal("fetch", async (input: Request) => {
    const key = `${input.method} ${new URL(input.url).pathname}`;
    calls.push({ key, req: input.clone() });
    const handler = routes[key];
    if (!handler) throw new Error(`mock 없는 요청: ${key}`);
    return handler(input);
  });
});
afterEach(() => vi.unstubAllGlobals());

const renderApp = () =>
  render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  );

const account = { 번호: 1, 아이디: "alice", 닉네임: "탐정" };

describe("로그인 화면", () => {
  it("토큰이 없으면 서버 확인 없이 로그인 화면을 보여 준다", async () => {
    renderApp();
    expect(await screen.findByRole("heading", { name: "로그인" })).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("로그인에 성공하면 토큰을 저장하고 닉네임을 보여 준다", async () => {
    routes["POST /api/auth/login"] = () => json({ 토큰: "tok-1", 만료일시: "2030-01-01T00:00:00Z", 계정: account });
    renderApp();
    await userEvent.type(await screen.findByLabelText("아이디"), "alice");
    await userEvent.type(screen.getByLabelText("패스워드"), "password123");
    await userEvent.click(screen.getByLabelText("자동 로그인"));
    await userEvent.click(screen.getByRole("button", { name: "로그인" }));

    expect(await screen.findByText("탐정")).toBeInTheDocument();
    expect(localStorage.getItem("mm.token")).toBe("tok-1");
    const body = await calls[0].req.json();
    expect(body).toEqual({ 아이디: "alice", 패스워드: "password123", 접속환경: "PC", 자동로그인: true });
  });

  it("로그인에 실패하면 서버 메시지를 보여 주고 토큰을 저장하지 않는다", async () => {
    routes["POST /api/auth/login"] = () => json({ detail: "아이디 또는 패스워드가 올바르지 않습니다" }, 401);
    renderApp();
    await userEvent.type(await screen.findByLabelText("아이디"), "alice");
    await userEvent.type(screen.getByLabelText("패스워드"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "로그인" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("아이디 또는 패스워드가 올바르지 않습니다");
    expect(localStorage.getItem("mm.token")).toBeNull();
  });
});

describe("회원가입", () => {
  it("가입 후 같은 정보로 로그인한다", async () => {
    routes["POST /api/auth/signup"] = () => json(account, 201);
    routes["POST /api/auth/login"] = () => json({ 토큰: "tok-2", 만료일시: "2030-01-01T00:00:00Z", 계정: account });
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "회원가입" }));
    await userEvent.type(screen.getByLabelText("아이디"), "alice");
    await userEvent.type(screen.getByLabelText("패스워드"), "password123");
    await userEvent.type(screen.getByLabelText("닉네임"), "탐정");
    await userEvent.click(screen.getByRole("button", { name: "가입하기" }));

    expect(await screen.findByText("탐정")).toBeInTheDocument();
    expect(calls.map((c) => c.key)).toEqual(["POST /api/auth/signup", "POST /api/auth/login"]);
  });

  it("아이디가 중복이면 오류를 보여 준다", async () => {
    routes["POST /api/auth/signup"] = () => json({ detail: "이미 사용 중인 아이디입니다" }, 409);
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "회원가입" }));
    await userEvent.type(screen.getByLabelText("아이디"), "alice");
    await userEvent.type(screen.getByLabelText("패스워드"), "password123");
    await userEvent.type(screen.getByLabelText("닉네임"), "탐정");
    await userEvent.click(screen.getByRole("button", { name: "가입하기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("이미 사용 중인 아이디입니다");
  });
});

describe("저장된 토큰", () => {
  it("유효하면 토큰을 Authorization 헤더로 보내 로그인 상태를 복원한다", async () => {
    localStorage.setItem("mm.token", "saved");
    routes["GET /api/auth/me"] = () => json(account);
    renderApp();
    expect(await screen.findByText("탐정")).toBeInTheDocument();
    expect(calls[0].req.headers.get("authorization")).toBe("Bearer saved");
  });

  it("만료되었으면 토큰을 지우고 로그인 화면으로 돌아간다", async () => {
    localStorage.setItem("mm.token", "expired");
    routes["GET /api/auth/me"] = () => json({ detail: "세션이 없거나 만료되었습니다" }, 401);
    renderApp();
    expect(await screen.findByRole("heading", { name: "로그인" })).toBeInTheDocument();
    expect(localStorage.getItem("mm.token")).toBeNull();
  });

  it("로그아웃하면 서버에 알리고 토큰을 지운다", async () => {
    localStorage.setItem("mm.token", "saved");
    routes["GET /api/auth/me"] = () => json(account);
    routes["POST /api/auth/logout"] = () => new Response(null, { status: 204 });
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "로그아웃" }));
    await waitFor(() => expect(localStorage.getItem("mm.token")).toBeNull());
    expect(await screen.findByRole("heading", { name: "로그인" })).toBeInTheDocument();
    expect(calls.map((c) => c.key)).toContain("POST /api/auth/logout");
  });
});
