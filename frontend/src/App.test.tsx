import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { answerConfirm } from "./confirmTest";

type Handler = (req: Request) => Response | Promise<Response>;
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

let routes: Record<string, Handler>;
const calls: { key: string; req: Request }[] = [];

beforeEach(() => {
  routes = {
    // 작품을 열면 기본으로 열리는 흐름 탭이 부르는 것들(이 파일의 시험은 내용이 아니라 화면 이동을 본다)
    "GET /api/content/schema": () => json({ resources: [], external: [] }),
    "GET /api/library/phases": () => json([]),
    "GET /api/library/gimmicks": () => json([]),
    "GET /api/works/7/content": () => json({ phases: [], "phase-steps": [], "gimmick-uses": [], library: { phases: {}, gimmicks: {} } }),
    "GET /api/works/7/confirm/check": () => json({ errors: [], warnings: [], 다음버전: "1.0" }),
    "GET /api/works/7/versions": () => json([]),
    "GET /api/play-works": () => json([]),
    "GET /api/works": () => json([]),
    "GET /api/private-play-works": () => json([]),
    "GET /api/rooms/me": () => json(null),
  };
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
afterEach(() => {
  cleanup(); // 화면(폴링 포함)을 먼저 정리한 뒤 모의 fetch 를 해제한다
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const renderApp = (path = "/") =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );

const account = { 번호: 1, 아이디: "alice", 닉네임: "탐정", 권한: "사용자" };

describe("로그인 화면", () => {
  it("토큰이 없으면 서버 확인 없이 로그인 화면을 보여 준다", async () => {
    renderApp();
    expect(await screen.findByRole("button", { name: "로그인" })).toBeInTheDocument();
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

describe("로그인 화면 구성과 다크 모드", () => {
  afterEach(() => {
    delete document.documentElement.dataset.theme;
    localStorage.removeItem("theme");
  });

  it("제목·로고·안내 문구 없이 입력칸만 보여 준다", async () => {
    renderApp();
    await screen.findByRole("button", { name: "로그인" });
    expect(screen.queryByRole("heading", { name: "로그인" })).not.toBeInTheDocument();
    expect(screen.queryByText(/함께 추리하세요/)).not.toBeInTheDocument();
    expect(document.querySelector(".brand-mark")).toBeNull();
  });

  it("라이트/다크 버튼: 켜면 유지, 다른 쪽을 누르면 바뀌고, 켜진 쪽을 누르면 꺼져서 시스템 설정을 따른다", async () => {
    renderApp();
    const light = await screen.findByRole("button", { name: "라이트 모드" });
    const dark = screen.getByRole("button", { name: "다크 모드" });
    const state = () => [light.getAttribute("aria-pressed"), dark.getAttribute("aria-pressed")];
    expect(state()).toEqual(["false", "false"]);               // 시작: 시스템
    expect(document.documentElement.dataset.theme).toBeUndefined();
    await userEvent.click(dark);
    expect(state()).toEqual(["false", "true"]);
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("theme")).toBe("dark");
    await userEvent.click(light);                               // 다른 쪽을 누르면 바뀐다
    expect(state()).toEqual(["true", "false"]);
    expect(document.documentElement.dataset.theme).toBe("light");
    await userEvent.click(light);                               // 켜진 쪽을 누르면 꺼진다 → 시스템
    expect(state()).toEqual(["false", "false"]);
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(localStorage.getItem("theme")).toBeNull();
  });

  it("탭 순서: 라이트/다크 버튼 → 아이디 → 패스워드", async () => {
    renderApp();
    const id = await screen.findByLabelText("아이디");
    const toggle = screen.getByRole("group", { name: "화면 모드" });
    expect(toggle.compareDocumentPosition(id) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();   // 버튼이 아이디보다 앞
    await userEvent.click(id);
    await userEvent.tab();
    expect(screen.getByLabelText("패스워드")).toHaveFocus();                                      // 아이디 다음은 패스워드
  });
});

describe("로그인 화면 오가기와 패스워드 찾기", () => {
  it("로그인과 회원가입 화면을 오가면 입력한 내용이 비워진다", async () => {
    renderApp();
    await userEvent.type(await screen.findByLabelText("아이디"), "alice");
    await userEvent.type(screen.getByLabelText("패스워드"), "secret");
    await userEvent.click(screen.getByRole("button", { name: "회원가입" }));
    expect(screen.getByLabelText("아이디")).toHaveValue("");
    expect(screen.getByLabelText("패스워드")).toHaveValue("");
    await userEvent.type(screen.getByLabelText("아이디"), "bob");
    await userEvent.type(screen.getByLabelText("닉네임"), "밥");
    await userEvent.click(screen.getByRole("button", { name: "로그인으로 돌아가기" }));
    expect(screen.getByLabelText("아이디")).toHaveValue("");
    await userEvent.click(screen.getByRole("button", { name: "회원가입" }));
    expect(screen.getByLabelText("닉네임")).toHaveValue("");
  });

  it("가입 화면에는 아이디·닉네임 길이 안내 문구가 없다", async () => {
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "회원가입" }));
    expect(screen.queryByText(/공백 없이 50자 이하/)).not.toBeInTheDocument();
  });

  it("로그인 실패 메시지(아이디 없음, 패스워드 오류, 잠김)를 그대로 보여 준다", async () => {
    let answer = { detail: "아이디가 존재하지 않습니다" };
    let status = 401;
    routes["POST /api/auth/login"] = () => json(answer, status);
    renderApp();
    await userEvent.type(await screen.findByLabelText("아이디"), "ghost");
    await userEvent.type(screen.getByLabelText("패스워드"), "x");
    await userEvent.click(screen.getByRole("button", { name: "로그인" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("아이디가 존재하지 않습니다");
    answer = { detail: "패스워드가 올바르지 않습니다 (남은 시도 9회)" };
    await userEvent.click(screen.getByRole("button", { name: "로그인" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("남은 시도 9회"));
    answer = { detail: "패스워드를 여러 번 틀려 잠시 막혔습니다. 5분 뒤에 다시 시도해 주세요" };
    status = 429;
    await userEvent.click(screen.getByRole("button", { name: "로그인" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("5분 뒤에 다시 시도"));
  });

  it("패스워드를 잊었을 때 아이디와 닉네임으로 새 패스워드를 정하고 로그인 화면으로 돌아간다", async () => {
    routes["POST /api/auth/reset-password"] = () => new Response(null, { status: 204 });
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "패스워드를 잊으셨나요?" }));
    await userEvent.type(screen.getByLabelText("아이디"), "alice");
    await userEvent.type(screen.getByLabelText("닉네임"), "탐정");
    await userEvent.type(screen.getByLabelText("새 패스워드"), "new-password");
    await userEvent.click(screen.getByRole("button", { name: "패스워드 바꾸기" }));
    expect(await screen.findByRole("status")).toHaveTextContent("패스워드를 바꿨습니다");
    expect(await calls.find((c) => c.key === "POST /api/auth/reset-password")!.req.json()).toEqual({ 아이디: "alice", 닉네임: "탐정", 새_패스워드: "new-password" });
    expect(screen.getByRole("button", { name: "로그인" })).toBeInTheDocument();
    expect(screen.getByLabelText("패스워드")).toHaveValue("");               // 새 패스워드는 다시 입력한다
    expect(screen.getByLabelText("아이디")).toHaveValue("alice");
  });

  it("아이디와 닉네임이 맞지 않으면 이유를 보여 주고 화면에 남는다", async () => {
    routes["POST /api/auth/reset-password"] = () => json({ detail: "닉네임이 맞지 않습니다 (남은 시도 9회)" }, 401);
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "패스워드를 잊으셨나요?" }));
    await userEvent.type(screen.getByLabelText("아이디"), "alice");
    await userEvent.type(screen.getByLabelText("닉네임"), "틀림");
    await userEvent.type(screen.getByLabelText("새 패스워드"), "new-password");
    await userEvent.click(screen.getByRole("button", { name: "패스워드 바꾸기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("닉네임이 맞지 않습니다 (남은 시도 9회)");
    expect(screen.getByRole("button", { name: "패스워드 바꾸기" })).toBeInTheDocument();
  });
});

describe("회원가입", () => {
  it("가입이 안 되면 어느 항목이 왜 문제인지 알려 준다", async () => {
    routes["POST /api/auth/signup"] = () =>
      json({ detail: [
        { type: "string_pattern_mismatch", loc: ["body", "아이디"], msg: "x", ctx: { pattern: "^\\S+$" } },
        { type: "string_too_short", loc: ["body", "패스워드"], msg: "x", ctx: { min_length: 8 } },
      ] }, 422);
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "회원가입" }));
    await userEvent.type(screen.getByLabelText("아이디"), "a b");
    await userEvent.type(screen.getByLabelText("패스워드"), "x");
    await userEvent.type(screen.getByLabelText("닉네임"), "A");
    await userEvent.click(screen.getByRole("button", { name: "가입하기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("아이디는 공백 없이 입력해 주세요 · 패스워드는 8자 이상이어야 합니다");
  });

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
    expect(calls.map((c) => c.key).filter((k) => k.includes("/api/auth/"))).toEqual(["POST /api/auth/signup", "POST /api/auth/login"]);
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
    expect(await screen.findByRole("button", { name: "로그인" })).toBeInTheDocument();
    expect(localStorage.getItem("mm.token")).toBeNull();
  });

  it("로그아웃하면 서버에 알리고 토큰을 지운다", async () => {
    localStorage.setItem("mm.token", "saved");
    routes["GET /api/auth/me"] = () => json(account);
    routes["POST /api/auth/logout"] = () => new Response(null, { status: 204 });
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "로그아웃" }));
    await waitFor(() => expect(localStorage.getItem("mm.token")).toBeNull());
    expect(await screen.findByRole("button", { name: "로그인" })).toBeInTheDocument();
    expect(calls.map((c) => c.key)).toContain("POST /api/auth/logout");
  });
});

const work = {
  번호: 7, 제목: "저택의 비밀", 시놉시스: "폭풍우 치는 밤", 장르: "추리", 최소인원: 1, 최대인원: 1,
  예상시간: "3시간", 상태: "개발", 공개여부: false, 공개권한: "제작자", 확정버전_있음: true, 생성일시: "2026-10-14T00:00:00Z", 수정일시: null,
};
const person = { 순서: 1, 이름: "홍길동", 직업: "의사", 나이: null, 성별: null, 서사: "", 타임라인: null, 능력: null, 비밀: null, 목표: null, 범인: false, NPC: false };

describe("작품", () => {
  beforeEach(() => {
    localStorage.setItem("mm.token", "saved");
    routes["GET /api/auth/me"] = () => json(account);
    routes["GET /api/works/7/testers"] = () => json([]);
  });

  it("작품 목록에 인원 범위와 상태를 보여 준다", async () => {
    routes["GET /api/works"] = () => json([work]);
    renderApp("/make/games");
    expect(await screen.findByText("저택의 비밀")).toBeInTheDocument();
    for (const chip of ["추리", "개발", "비공개", "인원 1~1명"]) expect(screen.getByText(chip)).toBeInTheDocument();
  });

  it("작품이 없으면 안내 문구를 보여 준다", async () => {
    renderApp("/make/games");
    expect(await screen.findByText("아직 작품이 없습니다.")).toBeInTheDocument();
  });

  it("작품 목록에서 확인 후 삭제하고, 서버가 거부하면 사유를 보여 준다", async () => {
    routes["GET /api/works"] = () => json([work, { ...work, 번호: 8, 제목: "방이 있는 작품" }]);
    routes["DELETE /api/works/7"] = () => new Response(null, { status: 204 });
    routes["DELETE /api/works/8"] = () => json({ detail: "이 작품으로 만든 방이나 플레이 기록이 있어 삭제할 수 없습니다" }, 409);
    renderApp("/make/games");
    await userEvent.click(await screen.findByRole("button", { name: "저택의 비밀 삭제" }));
    await answerConfirm(false);
    expect(calls.filter((c) => c.key === "DELETE /api/works/7")).toHaveLength(0);                         // 취소하면 보내지 않는다
    await userEvent.click(screen.getByRole("button", { name: "저택의 비밀 삭제" }));
    expect(await answerConfirm(true)).toBe("'저택의 비밀'을 삭제할까요?삭제된 내용은 복구할 수 없습니다.");              // 짧은 두 줄, 조사는 작품 이름에 맞춘다
    await waitFor(() => expect(screen.queryByText("저택의 비밀")).not.toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "방이 있는 작품 삭제" }));
    await answerConfirm(true);
    expect(await screen.findByRole("alert")).toHaveTextContent("방이나 플레이 기록이 있어");
    expect(screen.getByText("방이 있는 작품")).toBeInTheDocument();             // 목록에 그대로 남는다
  });

  it("새 작품을 누르면 입력을 받지 않고 바로 만들어 그 작품 화면(흐름)으로 이동한다", async () => {
    routes["POST /api/works"] = () => json({ ...work, 제목: "제목없음" }, 201);
    routes["GET /api/works/7"] = () => json(work);
    routes["GET /api/works/7/characters"] = () => json([]);
    renderApp("/make/games");
    await userEvent.click(await screen.findByRole("button", { name: "새 작품" }));
    expect(await screen.findByRole("tab", { name: "흐름", selected: true })).toBeInTheDocument();
    expect(await calls.find((c) => c.key === "POST /api/works")!.req.json()).toEqual({});     // 제목을 미리 받지 않는다
    expect(screen.queryByLabelText("제목")).not.toBeInTheDocument();
  });

  it("작품을 만들지 못하면 사유를 보여 주고 화면에 머문다", async () => {
    routes["POST /api/works"] = () => json({ detail: "작품을 만들지 못했습니다" }, 500);
    renderApp("/make/games");
    await userEvent.click(await screen.findByRole("button", { name: "새 작품" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("작품을 만들지 못했습니다");
  });

  it("인물을 추가하면 목록과 최대 인원이 갱신된다", async () => {
    let people: unknown[] = [];
    let current: Record<string, unknown> = work;
    routes["GET /api/works/7"] = () => json(current);
    routes["GET /api/works/7/characters"] = () => json(people);
    routes["POST /api/works/7/characters"] = () => {
      people = [person];
      current = { ...work, 최대인원: 1 };
      return json(person, 201);
    };
    renderApp("/works/7?tab=characters");
    expect(await screen.findByText("아직 인물이 없습니다.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "인물 추가" }));
    const form = screen.getByRole("form", { name: "인물 추가" });
    await userEvent.type(within(form).getByLabelText("이름"), "홍길동");
    await userEvent.type(within(form).getByLabelText("직업"), "의사");
    await userEvent.click(within(form).getByRole("button", { name: "저장" }));

    expect(await screen.findByText("홍길동")).toBeInTheDocument();
    const body = await calls.find((c) => c.key === "POST /api/works/7/characters")!.req.json();
    expect(body).toMatchObject({ 이름: "홍길동", 직업: "의사", 성별: null, 나이: null, 범인: false, NPC: false });
  });

  it("기본정보를 저장하면 안내를 보여 주고, 이후 목록을 다시 불러와도 입력이 유지된다", async () => {
    let current: Record<string, unknown> = work;
    routes["GET /api/works/7"] = () => json(current);
    routes["GET /api/works/7/characters"] = () => json([]);
    routes["PATCH /api/works/7"] = () => {
      current = { ...work, 수정일시: "2026-10-14T01:00:00Z" }; // 저장하면 수정일시가 바뀐다
      return json(current);
    };
    renderApp("/works/7?tab=confirm");
    const form = await screen.findByRole("form", { name: "기본정보" });
    await userEvent.type(within(form).getByLabelText("장르"), "!");
    await userEvent.click(within(form).getByRole("button", { name: "저장" }));
    expect(await within(form).findByRole("status")).toHaveTextContent("저장했습니다");
    expect(within(form).getByLabelText("장르")).toHaveValue("추리!");
  });

  it("기본정보에서 시간 형식을 고르면 저장할 때 함께 보낸다", async () => {
    routes["GET /api/works/7"] = () => json({ ...work, 시간형식: "시간만" });
    routes["GET /api/works/7/characters"] = () => json([]);
    routes["PATCH /api/works/7"] = () => json({ ...work, 시간형식: "월까지" });
    renderApp("/works/7?tab=confirm");
    const form = await screen.findByRole("form", { name: "기본정보" });
    expect(within(form).getByLabelText("시간 형식")).toHaveValue("시간만");
    expect(within(form).getAllByRole("option").filter((o) => ["시간만", "일까지", "월까지", "연도까지"].includes(o.textContent ?? ""))).toHaveLength(4);
    await userEvent.selectOptions(within(form).getByLabelText("시간 형식"), "월까지");
    await userEvent.click(within(form).getByRole("button", { name: "저장" }));
    await within(form).findByRole("status");
    expect((await calls.find((c) => c.key === "PATCH /api/works/7")!.req.json()).시간형식).toBe("월까지");
  });

  it("기본정보 저장은 공개여부를 보내지 않는다", async () => {
    routes["GET /api/works/7"] = () => json(work);
    routes["GET /api/works/7/characters"] = () => json([]);
    routes["PATCH /api/works/7"] = () => json(work);
    renderApp("/works/7?tab=confirm");
    const form = await screen.findByRole("form", { name: "기본정보" });
    await userEvent.click(within(form).getByRole("button", { name: "저장" }));
    await within(form).findByRole("status");
    const sent = await calls.find((c) => c.key === "PATCH /api/works/7")!.req.json();
    expect(sent).not.toHaveProperty("공개여부");
    expect(sent).not.toHaveProperty("공개권한");
  });

  it("비공개 작품은 공개하기로 공개하고 공개 중으로 바뀐다", async () => {
    let current: Record<string, unknown> = work;
    routes["GET /api/works/7"] = () => json(current);
    routes["GET /api/works/7/characters"] = () => json([]);
    routes["POST /api/works/7/publish"] = () => {
      current = { ...work, 공개여부: true };
      return json(current);
    };
    renderApp("/works/7?tab=confirm");
    const panel = await screen.findByRole("region", { name: "공개 상태" });
    await userEvent.click(within(panel).getByRole("button", { name: "공개하기" }));
    expect(await within(panel).findByText("공개 중")).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "비공개로 전환" })).toBeInTheDocument();
  });

  it("확정된 버전이 없으면 공개하기 버튼을 쓸 수 없고 이유를 보여 준다", async () => {
    routes["GET /api/works/7"] = () => json({ ...work, 확정버전_있음: false });
    routes["GET /api/works/7/characters"] = () => json([]);
    renderApp("/works/7?tab=confirm");
    const panel = await screen.findByRole("region", { name: "공개 상태" });
    expect(within(panel).getByRole("button", { name: "공개하기" })).toBeDisabled();
    expect(within(panel).getByText("확정된 버전이 없어 공개할 수 없습니다.")).toBeInTheDocument();
  });

  it("관리자가 비공개한 작품은 제작자에게 공개 버튼이 없다", async () => {
    routes["GET /api/works/7"] = () => json({ ...work, 공개권한: "관리자" });
    routes["GET /api/works/7/characters"] = () => json([]);
    renderApp("/works/7?tab=confirm");
    const panel = await screen.findByRole("region", { name: "공개 상태" });
    expect(within(panel).getByText(/관리자가 비공개 처리했습니다/)).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "공개하기" })).not.toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: /돌려주기/ })).not.toBeInTheDocument();
  });

  it("관리자 권한이 있어도 자기 작품은 제작자 자격이라 관리자가 비공개한 작품을 공개할 수 없다", async () => {
    routes["GET /api/auth/me"] = () => json({ ...account, 권한: "관리자" });
    routes["GET /api/works/7"] = () => json({ ...work, 공개권한: "관리자" });
    routes["GET /api/works/7/characters"] = () => json([]);
    renderApp("/works/7?tab=confirm");
    const panel = await screen.findByRole("region", { name: "공개 상태" });
    expect(within(panel).queryByRole("button", { name: "공개하기" })).not.toBeInTheDocument();
  });

  it("운영자는 자기 작품에서 운영자가 비공개한 작품을 공개하거나 제작자에게 돌려줄 수 있다", async () => {
    routes["GET /api/auth/me"] = () => json({ ...account, 권한: "운영자" });
    routes["GET /api/works/7"] = () => json({ ...work, 공개권한: "운영자" });
    routes["GET /api/works/7/characters"] = () => json([]);
    renderApp("/works/7?tab=confirm");
    const panel = await screen.findByRole("region", { name: "공개 상태" });
    expect(within(panel).getByRole("button", { name: "공개하기" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "제작자에게 공개 권한 돌려주기" })).toBeInTheDocument();
  });

  it("서버가 공개를 거부하면 사유를 보여 준다", async () => {
    routes["GET /api/works/7"] = () => json(work);
    routes["GET /api/works/7/characters"] = () => json([]);
    routes["POST /api/works/7/publish"] = () => json({ detail: "이 작품에 대한 권한이 없습니다" }, 403);
    renderApp("/works/7?tab=confirm");
    const panel = await screen.findByRole("region", { name: "공개 상태" });
    await userEvent.click(within(panel).getByRole("button", { name: "공개하기" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent("이 작품에 대한 권한이 없습니다");
  });

  it("테스터를 아이디로 추가하고 삭제한다", async () => {
    let testers: unknown[] = [];
    routes["GET /api/works/7"] = () => json(work);
    routes["GET /api/works/7/characters"] = () => json([]);
    routes["GET /api/works/7/testers"] = () => json(testers);
    routes["POST /api/works/7/testers"] = () => {
      const t = { 계정_번호: 5, 아이디: "bob", 닉네임: "밥", 부여일시: "2026-10-14T00:00:00Z" };
      testers = [t];
      return json(t, 201);
    };
    routes["DELETE /api/works/7/testers/5"] = () => {
      testers = [];
      return new Response(null, { status: 204 });
    };
    renderApp("/works/7?tab=confirm");
    const panel = await screen.findByRole("region", { name: "테스터" });
    await userEvent.type(within(panel).getByLabelText("테스터 아이디"), "bob");
    await userEvent.click(within(panel).getByRole("button", { name: "추가" }));
    expect(await within(panel).findByText("bob")).toBeInTheDocument();
    expect(await calls.find((c) => c.key === "POST /api/works/7/testers")!.req.json()).toEqual({ 아이디: "bob" });
    await userEvent.click(within(panel).getByRole("button", { name: "삭제" }));
    await waitFor(() => expect(within(panel).queryByText("bob")).not.toBeInTheDocument());
  });

  it("없는 아이디를 테스터로 추가하면 오류를 보여 준다", async () => {
    routes["GET /api/works/7"] = () => json(work);
    routes["GET /api/works/7/characters"] = () => json([]);
    routes["POST /api/works/7/testers"] = () => json({ detail: "해당 아이디의 계정이 없습니다" }, 404);
    renderApp("/works/7?tab=confirm");
    const panel = await screen.findByRole("region", { name: "테스터" });
    await userEvent.type(within(panel).getByLabelText("테스터 아이디"), "nobody");
    await userEvent.click(within(panel).getByRole("button", { name: "추가" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent("해당 아이디의 계정이 없습니다");
  });

  it("플레이공간 첫 화면: 방을 만들 수 있는 작품(공개·비공개 플레이)을 보여 준다", async () => {
    routes["GET /api/play-works"] = () => json([
      { 번호: 8, 제목: "공개 작품", 시놉시스: "", 장르: "추리", 최소인원: 2, 최대인원: 4, 예상시간: "2시간", 제작자: "탐정", 비공개플레이: false },
      { 번호: 9, 제목: "테스트 작품", 시놉시스: "", 장르: "", 최소인원: 1, 최대인원: 3, 예상시간: "1시간", 제작자: "나", 비공개플레이: true },
    ]);
    renderApp();
    expect(await screen.findByRole("heading", { name: "플레이" })).toBeInTheDocument();
    expect(screen.queryByLabelText("입장코드")).not.toBeInTheDocument();             // 입장코드 입력은 버튼을 눌러야 나온다
    expect(screen.getByRole("button", { name: "입장코드" })).toBeInTheDocument();
    expect(await screen.findByText("공개 작품")).toBeInTheDocument();
    expect(screen.getByText("제작 탐정")).toBeInTheDocument();
    expect(screen.getAllByText("비공개 플레이")).toHaveLength(1);                       // 테스트 작품에만 붙는다
    const links = screen.getAllByRole("link", { name: "방 만들기" });
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["/rooms/new/8", "/rooms/new/9"]);
  });

  it("플레이할 작품이 없으면 안내한다", async () => {
    renderApp();
    expect(await screen.findByText("지금 플레이할 수 있는 작품이 없습니다.")).toBeInTheDocument();
  });

  it("상단에서 플레이공간·제작공간·기록공간으로 오가고, 제작공간에는 게임 만들기와 라이브러리 만들기가 있다", async () => {
    renderApp();
    const nav = within(await screen.findByRole("navigation", { name: "공간" }));
    expect(nav.getAllByRole("link").map((l) => l.textContent)).toEqual(["플레이공간", "제작공간", "기록공간"]);
    await userEvent.click(nav.getByRole("link", { name: "제작공간" }));
    expect(await screen.findByRole("link", { name: /게임 만들기/ })).toHaveAttribute("href", "/make/games");
    expect(screen.getByRole("link", { name: /라이브러리 만들기/ })).toHaveAttribute("href", "/make/library");
    await userEvent.click(nav.getByRole("link", { name: "기록공간" }));
    expect(await screen.findByText("아직 기록이 없습니다.")).toBeInTheDocument();
  });

  it("서버가 거부하면 기본정보 저장 오류를 보여 준다", async () => {
    routes["GET /api/works/7"] = () => json(work);
    routes["GET /api/works/7/characters"] = () => json([]);
    routes["PATCH /api/works/7"] = () => json({ detail: "저장할 수 없습니다" }, 409);
    renderApp("/works/7?tab=confirm");
    const form = await screen.findByRole("form", { name: "기본정보" });
    await userEvent.type(within(form).getByLabelText("장르"), "추리");
    await userEvent.click(within(form).getByRole("button", { name: "저장" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("저장할 수 없습니다");
  });

  it("플레이 인원은 직접 입력하지 않고 인물에서 계산된 값으로 보인다", async () => {
    routes["GET /api/works/7"] = () => json({ ...work, 최소인원: 3, 최대인원: 5 });
    routes["GET /api/works/7/characters"] = () => json([]);
    renderApp("/works/7?tab=confirm");
    const form = await screen.findByRole("form", { name: "기본정보" });
    expect(within(form).queryByLabelText("최소 인원")).not.toBeInTheDocument();
    expect(within(form).getByText("3~5명")).toBeInTheDocument();
  });

  it("없는 작품이면 오류와 목록 링크를 보여 준다", async () => {
    routes["GET /api/works/99"] = () => json({ detail: "작품을 찾을 수 없습니다" }, 404);
    routes["GET /api/works/99/characters"] = () => json({ detail: "작품을 찾을 수 없습니다" }, 404);
    renderApp("/works/99?tab=confirm");
    expect(await screen.findByRole("alert")).toHaveTextContent("작품을 찾을 수 없습니다");
  });
});


const baseRoom = {
  번호: 1, 입장코드: "K7M2QX", 상태: "대기",
  작품: { 번호: 7, 제목: "저택의 비밀", 시놉시스: "", 장르: "추리", 예상시간: "3시간", 최소인원: 3, 최대인원: 4 },
  버전: "1.0", 내가_방장: true,
  참가자: [{ 계정_번호: 1, 닉네임: "탐정", 방장: true, 플레이: true }],
  플레이어_수: 1, 생성일시: "2026-10-14T00:00:00Z",
};

describe("방", () => {
  beforeEach(() => {
    localStorage.setItem("mm.token", "saved");
    routes["GET /api/auth/me"] = () => json(account);
  });

  it("플레이공간의 입장코드 버튼은 입장코드 입력 창을 열고 닫을 수 있다", async () => {
    renderApp();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "입장코드" }));
    const dialog = screen.getByRole("dialog", { name: "입장코드로 입장" });
    expect(within(dialog).getByLabelText("입장코드")).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "입장코드" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "닫기" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("입장 창에서 코드를 넣으면 입장해서 대기실로 간다", async () => {
    let inRoom = false;
    const asGuest = { ...baseRoom, 내가_방장: false };
    routes["GET /api/rooms/me"] = () => json(inRoom ? asGuest : null);
    routes["POST /api/rooms/join"] = () => {
      inRoom = true;
      return json(asGuest);
    };
    renderApp();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "입장코드" }));
    await user.type(screen.getByLabelText("입장코드"), "k7m2qx");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "입장하기" }));
    expect(await screen.findByRole("heading", { name: "저택의 비밀" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(await calls.find((c) => c.key === "POST /api/rooms/join")!.req.json()).toEqual({ 입장코드: "K7M2QX", 관전: false });
  });

  it("입장 창에서 코드가 틀리면 창 안에 이유를 보여 준다", async () => {
    routes["POST /api/rooms/join"] = () => json({ detail: "입장코드가 올바르지 않습니다" }, 404);
    renderApp();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "입장코드" }));
    await user.type(screen.getByLabelText("입장코드"), "ZZZZZZ");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "입장하기" }));
    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent("입장코드가 올바르지 않습니다");
  });

  it("입장 창에는 안내 글과 예시가 없다", async () => {
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "입장코드" }));
    expect(screen.queryByText(/6자리/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("입장코드")).not.toHaveAttribute("placeholder");
  });

  it("진행 중인 방이면 그렇게 안내하고 관전 참여 버튼으로 관전자로 들어간다", async () => {
    let inRoom = false;
    const running = { ...baseRoom, 상태: "진행", 내가_방장: false };
    routes["GET /api/rooms/me"] = () => json(inRoom ? running : null);
    routes["POST /api/rooms/join"] = async (req) => {
      if (!(await req.clone().json()).관전) return json({ detail: "진행 중인 방입니다." }, 409);
      inRoom = true;
      return json(running);
    };
    routes["GET /api/game/me/state"] = () => json({}, 404);
    renderApp();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "입장코드" }));
    await user.type(screen.getByLabelText("입장코드"), "k7m2qx");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "입장하기" }));
    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent("진행 중인 방입니다.");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "관전 참여" }));
    await waitFor(() => expect(calls.filter((c) => c.key === "POST /api/rooms/join")).toHaveLength(2));
    expect(await calls.filter((c) => c.key === "POST /api/rooms/join")[1].req.json()).toEqual({ 입장코드: "K7M2QX", 관전: true });
  });

  it("다른 이유로 입장하지 못하면 관전 참여 버튼은 나오지 않는다", async () => {
    routes["POST /api/rooms/join"] = () => json({ detail: "다른 방에 참여 중입니다." }, 409);
    renderApp();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "입장코드" }));
    await user.type(screen.getByLabelText("입장코드"), "k7m2qx");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "입장하기" }));
    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent("다른 방에 참여 중입니다.");
    expect(screen.queryByRole("button", { name: "관전 참여" })).not.toBeInTheDocument();
  });

  it("방장이 준 링크를 열면 바로 입장해서 대기실로 간다", async () => {
    let inRoom = false;
    const asGuest = { ...baseRoom, 내가_방장: false };
    routes["GET /api/rooms/me"] = () => json(inRoom ? asGuest : null);
    routes["POST /api/rooms/join"] = () => {
      inRoom = true;
      return json(asGuest);
    };
    renderApp("/join/K7M2QX");
    expect(await screen.findByRole("heading", { name: "저택의 비밀" })).toBeInTheDocument();
    expect(calls.filter((c) => c.key === "POST /api/rooms/join")).toHaveLength(1);
    expect(await calls.find((c) => c.key === "POST /api/rooms/join")!.req.json()).toEqual({ 입장코드: "K7M2QX", 관전: false });
  });

  it("링크로 들어왔는데 진행 중인 방이면 안내와 관전 참여 버튼이 나온다", async () => {
    routes["POST /api/rooms/join"] = () => json({ detail: "진행 중인 방입니다." }, 409);
    renderApp("/join/K7M2QX");
    expect(await screen.findByRole("alert")).toHaveTextContent("진행 중인 방입니다.");
    expect(screen.getByRole("button", { name: "관전 참여" })).toBeInTheDocument();
  });

  it("로그인하지 않은 채로 링크를 열면 로그인 화면이 먼저 나오고, 로그인하면 바로 그 방에 입장한다", async () => {
    localStorage.clear();
    let inRoom = false;
    const asGuest = { ...baseRoom, 내가_방장: false };
    routes["GET /api/rooms/me"] = () => json(inRoom ? asGuest : null);
    routes["POST /api/auth/login"] = () => json({ 토큰: "tok-1", 만료일시: "2030-01-01T00:00:00Z", 계정: account });
    routes["POST /api/rooms/join"] = () => {
      inRoom = true;
      return json(asGuest);
    };
    renderApp("/join/K7M2QX");
    await userEvent.type(await screen.findByLabelText("아이디"), "alice");
    await userEvent.type(screen.getByLabelText("패스워드"), "password123");
    await userEvent.click(screen.getByRole("button", { name: "로그인" }));
    expect(await screen.findByRole("heading", { name: "저택의 비밀" })).toBeInTheDocument();
    expect(await calls.find((c) => c.key === "POST /api/rooms/join")!.req.json()).toEqual({ 입장코드: "K7M2QX", 관전: false });
  });

  it("대기실의 링크 복사 버튼은 입장 링크를 복사한다", async () => {
    routes["GET /api/rooms/me"] = () => json(baseRoom);
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderApp("/room");
    await userEvent.click(await screen.findByRole("button", { name: "링크 복사" }));
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/join/K7M2QX`);
  });

  it("입장코드를 대문자로 바꿔 입장하고 대기실을 보여 준다", async () => {
    let inRoom = false;
    const asGuest = { ...baseRoom, 내가_방장: false };
    routes["GET /api/rooms/me"] = () => json(inRoom ? asGuest : null);
    routes["POST /api/rooms/join"] = () => {
      inRoom = true;
      return json(asGuest);
    };
    renderApp("/rooms/join");
    await userEvent.type(await screen.findByLabelText("입장코드"), "k7m2qx");
    expect(screen.getByLabelText("입장코드")).toHaveValue("K7M2QX");
    await userEvent.click(screen.getByRole("button", { name: "입장하기" }));
    expect(await screen.findByRole("heading", { name: "저택의 비밀" })).toBeInTheDocument();
    expect(await calls.find((c) => c.key === "POST /api/rooms/join")!.req.json()).toEqual({ 입장코드: "K7M2QX", 관전: false });
    expect(screen.getByRole("button", { name: "나가기" })).toBeInTheDocument();
  });

  it("입장코드가 틀리거나 너무 많이 틀리면 서버 메시지를 보여 준다", async () => {
    routes["POST /api/rooms/join"] = () => json({ detail: "입장코드가 올바르지 않습니다" }, 404);
    renderApp("/rooms/join");
    await userEvent.type(await screen.findByLabelText("입장코드"), "ZZZZZZ");
    await userEvent.click(screen.getByRole("button", { name: "입장하기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("입장코드가 올바르지 않습니다");
  });

  it("방 만들기: 방장도 플레이어로 참여하는 것으로 만들고 대기실로 간다(설명 글과 참여 선택은 없다)", async () => {
    let inRoom = false;
    routes["GET /api/rooms/me"] = () => json(inRoom ? baseRoom : null);
    routes["POST /api/rooms"] = () => {
      inRoom = true;
      return json(baseRoom, 201);
    };
    renderApp("/rooms/new/7");
    expect(await screen.findByText(/입장 코드는 4~10자로 지정 가능합니다\./)).toBeInTheDocument();
    expect(screen.getByText(/미 입력시 자동 생성됩니다\./)).toBeInTheDocument();
    expect(screen.queryByLabelText("나도 플레이어로 참여")).not.toBeInTheDocument();
    expect(screen.queryByText(/으로 방을 만듭니다/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("입장코드")).not.toHaveAttribute("placeholder");
    await userEvent.click(screen.getByRole("button", { name: "방 만들기" }));
    expect(await screen.findByRole("heading", { name: "저택의 비밀" })).toBeInTheDocument();
    expect(await calls.find((c) => c.key === "POST /api/rooms")!.req.json()).toEqual({ 작품_번호: 7, 방장_참여: true, 입장코드: null });
  });

  it("방 만들기 화면의 제목 자리에는 작품 제목이 들어간다(목록에서 눌러 오면 그대로, 주소로 오면 불러와서)", async () => {
    routes["GET /api/play-works"] = () => json([{ 번호: 7, 제목: "저택의 비밀", 시놉시스: "", 장르: "추리", 예상시간: "3시간", 최소인원: 3, 최대인원: 4, 제작자: "탐정", 비공개플레이: false }]);
    renderApp("/");
    await userEvent.click(await screen.findByRole("link", { name: "방 만들기" }));
    expect(await screen.findByRole("heading", { name: "저택의 비밀", level: 1 })).toBeInTheDocument();
    cleanup();
    routes["GET /api/private-play-works"] = () => json([{ 번호: 7, 제목: "주소로 열린 작품" }]);
    renderApp("/rooms/new/7");
    expect(await screen.findByRole("heading", { name: "주소로 열린 작품", level: 1 })).toBeInTheDocument();
  });

  it("방장이 입장코드를 정하면 대문자로 바꿔 보내고, 이미 쓰는 코드면 이유를 보여 준다", async () => {
    routes["POST /api/rooms"] = () => json({ detail: "이미 사용 중인 입장코드입니다. 다른 코드를 정해 주세요" }, 409);
    renderApp("/rooms/new/7");
    await userEvent.type(await screen.findByLabelText("입장코드"), "friends7");
    expect(screen.getByLabelText("입장코드")).toHaveValue("FRIENDS7");
    await userEvent.click(screen.getByRole("button", { name: "방 만들기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("이미 사용 중인 입장코드");
    expect(await calls.find((c) => c.key === "POST /api/rooms")!.req.json()).toEqual({ 작품_번호: 7, 방장_참여: true, 입장코드: "FRIENDS7" });
  });

  it("입장코드 길이가 맞지 않으면 어느 항목이 왜 안 되는지 알려 준다", async () => {
    routes["POST /api/rooms"] = () => json({ detail: [{ type: "string_too_short", loc: ["body", "입장코드"], msg: "x", ctx: { min_length: 4 } }] }, 422);
    renderApp("/rooms/new/7");
    await userEvent.type(await screen.findByLabelText("입장코드"), "AB");
    await userEvent.click(screen.getByRole("button", { name: "방 만들기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("입장코드는 4자 이상이어야 합니다");
  });

  it("방을 만들 수 없으면 사유를 보여 준다", async () => {
    routes["POST /api/rooms"] = () => json({ detail: "확정된 버전이 없는 작품으로는 방을 만들 수 없습니다" }, 409);
    renderApp("/rooms/new/7");
    await userEvent.click(await screen.findByRole("button", { name: "방 만들기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("확정된 버전이 없는");
  });

  it("작품 상세에서 확정 버전이 없으면 방 만들기가 막히고 이유가 보인다", async () => {
    routes["GET /api/works/7"] = () => json({ ...work, 확정버전_있음: false });
    routes["GET /api/works/7/characters"] = () => json([]);
    routes["GET /api/works/7/testers"] = () => json([]);
    renderApp("/works/7?tab=confirm");
    const panel = await screen.findByRole("region", { name: "방" });
    expect(within(panel).getByRole("button", { name: "방 만들기" })).toBeDisabled();
    expect(within(panel).getByText("확정된 버전이 없어 방을 만들 수 없습니다.")).toBeInTheDocument();
  });

  it("작품 상세에서 확정 버전이 있으면 방 만들기로 이동할 수 있다", async () => {
    routes["GET /api/works/7"] = () => json(work);
    routes["GET /api/works/7/characters"] = () => json([]);
    routes["GET /api/works/7/testers"] = () => json([]);
    renderApp("/works/7?tab=confirm");
    const panel = await screen.findByRole("region", { name: "방" });
    expect(within(panel).getByRole("link", { name: "이 작품으로 방 만들기" })).toHaveAttribute("href", "/rooms/new/7");
  });

  it("관리자가 비공개한 작품은 제작자에게 방 만들기를 막는다", async () => {
    routes["GET /api/works/7"] = () => json({ ...work, 공개권한: "관리자" });
    routes["GET /api/works/7/characters"] = () => json([]);
    routes["GET /api/works/7/testers"] = () => json([]);
    renderApp("/works/7?tab=confirm");
    const panel = await screen.findByRole("region", { name: "방" });
    expect(within(panel).getByRole("button", { name: "방 만들기" })).toBeDisabled();
    expect(within(panel).getByText(/관리자가 비공개 처리한 작품은/)).toBeInTheDocument();
  });

  it("대기실: 방장은 코드와 참가자, 인원, 방 닫기를 본다", async () => {
    routes["GET /api/rooms/me"] = () => json({
      ...baseRoom,
      참가자: [
        { 계정_번호: 1, 닉네임: "탐정", 방장: true, 플레이: true },
        { 계정_번호: 2, 닉네임: "의사", 방장: false, 플레이: true },
      ],
      플레이어_수: 2,
    });
    renderApp("/room");
    expect(await screen.findByLabelText("입장코드", { selector: "strong" })).toHaveTextContent("K7M2QX");
    const list = screen.getByRole("region", { name: "참가자" });
    expect(within(list).getByText("의사")).toBeInTheDocument();
    expect(within(list).getByText("플레이어 2/4명")).toBeInTheDocument();
    expect(within(list).getByRole("button", { name: "방 닫기" })).toBeInTheDocument();
    expect(within(list).getByLabelText("나도 플레이어로 참여")).toBeChecked();
  });

  it("대기실은 주기적으로 갱신되어 새 입장자를 보여 준다", async () => {
    let members = [{ 계정_번호: 1, 닉네임: "탐정", 방장: true, 플레이: true }];
    routes["GET /api/rooms/me"] = () => json({ ...baseRoom, 참가자: members, 플레이어_수: members.length });
    renderApp("/room");
    await screen.findByText("탐정");
    expect(screen.queryByText("의사")).not.toBeInTheDocument();
    members = [...members, { 계정_번호: 2, 닉네임: "의사", 방장: false, 플레이: true }];
    expect(await screen.findByText("의사")).toBeInTheDocument();
  });

  it("방이 닫히면 대기실이 안내 화면으로 바뀐다", async () => {
    let open = true;
    routes["GET /api/rooms/me"] = () => json(open ? baseRoom : null);
    renderApp("/room");
    await screen.findByRole("heading", { name: "저택의 비밀" });
    open = false;
    expect(await screen.findByText("참여 중인 방이 없습니다.")).toBeInTheDocument();
  });

  it("방장이 방 닫기를 누르면 확인 후 서버에 알리고 목록으로 돌아간다", async () => {
    let open = true;
    routes["GET /api/rooms/me"] = () => json(open ? baseRoom : null);
    routes["POST /api/rooms/leave"] = () => {
      open = false;
      return new Response(null, { status: 204 });
    };
    renderApp("/room");
    await userEvent.click(await screen.findByRole("button", { name: "방 닫기" }));
    await answerConfirm(true);
    expect(await screen.findByRole("heading", { name: "플레이" })).toBeInTheDocument();     // 방을 닫으면 플레이공간으로
    expect(calls.map((c) => c.key)).toContain("POST /api/rooms/leave");
  });

  it("확인을 취소하면 방을 닫지 않는다", async () => {
    routes["GET /api/rooms/me"] = () => json(baseRoom);
    renderApp("/room");
    await userEvent.click(await screen.findByRole("button", { name: "방 닫기" }));
    await answerConfirm(false);
    expect(calls.map((c) => c.key)).not.toContain("POST /api/rooms/leave");
  });

  it("방장은 플레이 참여 여부를 바꾼다", async () => {
    routes["GET /api/rooms/me"] = () => json(baseRoom);
    routes["PATCH /api/rooms/me"] = () => json(baseRoom);
    renderApp("/room");
    await userEvent.click(await screen.findByLabelText("나도 플레이어로 참여"));
    await waitFor(() => expect(calls.map((c) => c.key)).toContain("PATCH /api/rooms/me"));
    expect(await calls.find((c) => c.key === "PATCH /api/rooms/me")!.req.json()).toEqual({ 플레이: false });
  });

  it("방에 있으면 상단에 내 방 코드가 보인다", async () => {
    routes["GET /api/rooms/me"] = () => json(baseRoom);
    renderApp("/");
    expect(await screen.findByRole("link", { name: "내 방" })).toHaveTextContent("K7M2QX");
  });

});
