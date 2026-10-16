import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";

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

  it("아이디 칸과 같은 줄에 있다", async () => {
    renderApp();
    const row = (await screen.findByLabelText("아이디")).closest(".id-row")!;
    expect(row.querySelector('[role="group"][aria-label="화면 모드"]')).not.toBeNull();
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
    renderApp();
    expect(await screen.findByText("저택의 비밀")).toBeInTheDocument();
    for (const chip of ["추리", "개발", "비공개", "인원 1~1명"]) expect(screen.getByText(chip)).toBeInTheDocument();
  });

  it("작품이 없으면 안내 문구를 보여 준다", async () => {
    renderApp();
    expect(await screen.findByText("아직 작품이 없습니다.")).toBeInTheDocument();
  });

  it("작품 목록에서 확인 후 삭제하고, 서버가 거부하면 사유를 보여 준다", async () => {
    routes["GET /api/works"] = () => json([work, { ...work, 번호: 8, 제목: "방이 있는 작품" }]);
    // 내 작품은 비공개 플레이 목록에도 내려오지만, 위 목록에 없어지면 그쪽에 따로 나타나므로 함께 지워야 한다
    routes["GET /api/private-play-works"] = () => json([{ ...work }]);
    routes["DELETE /api/works/7"] = () => new Response(null, { status: 204 });
    routes["DELETE /api/works/8"] = () => json({ detail: "이 작품으로 만든 방이나 플레이 기록이 있어 삭제할 수 없습니다" }, 409);
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValue(true);
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "저택의 비밀 삭제" }));
    expect(calls.filter((c) => c.key === "DELETE /api/works/7")).toHaveLength(0);                         // 취소하면 보내지 않는다
    await userEvent.click(screen.getByRole("button", { name: "저택의 비밀 삭제" }));
    await waitFor(() => expect(screen.queryByText("저택의 비밀")).not.toBeInTheDocument());
    expect(confirm.mock.calls[1][0]).toContain("저택의 비밀");
    await userEvent.click(screen.getByRole("button", { name: "방이 있는 작품 삭제" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("방이나 플레이 기록이 있어");
    expect(screen.getByText("방이 있는 작품")).toBeInTheDocument();             // 목록에 그대로 남는다
  });

  it("새 작품을 만들면 그 작품 화면으로 이동한다", async () => {
    routes["POST /api/works"] = () => json(work, 201);
    routes["GET /api/works/7"] = () => json(work);
    routes["GET /api/works/7/characters"] = () => json([]);
    renderApp("/works/new");
    await userEvent.type(await screen.findByLabelText("제목"), "저택의 비밀");
    await userEvent.click(screen.getByRole("button", { name: "만들기" }));
    expect(await screen.findByRole("tab", { name: "흐름", selected: true })).toBeInTheDocument();   // 게임 흐름이 기본 탭
    expect(calls.find((c) => c.key === "POST /api/works")).toBeDefined();
    expect(await calls.find((c) => c.key === "POST /api/works")!.req.json()).toEqual({ 제목: "저택의 비밀" });
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
    renderApp("/works/7?tab=overview");
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
    renderApp("/works/7?tab=overview");
    const form = await screen.findByRole("form", { name: "기본정보" });
    await userEvent.type(within(form).getByLabelText("장르"), "!");
    await userEvent.click(within(form).getByRole("button", { name: "저장" }));
    expect(await within(form).findByRole("status")).toHaveTextContent("저장했습니다");
    expect(within(form).getByLabelText("장르")).toHaveValue("추리!");
  });

  it("기본정보 저장은 공개여부를 보내지 않는다", async () => {
    routes["GET /api/works/7"] = () => json(work);
    routes["GET /api/works/7/characters"] = () => json([]);
    routes["PATCH /api/works/7"] = () => json(work);
    renderApp("/works/7?tab=overview");
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
    renderApp("/works/7?tab=overview");
    const panel = await screen.findByRole("region", { name: "공개 상태" });
    await userEvent.click(within(panel).getByRole("button", { name: "공개하기" }));
    expect(await within(panel).findByText("공개 중")).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "비공개로 전환" })).toBeInTheDocument();
  });

  it("확정된 버전이 없으면 공개하기 버튼을 쓸 수 없고 이유를 보여 준다", async () => {
    routes["GET /api/works/7"] = () => json({ ...work, 확정버전_있음: false });
    routes["GET /api/works/7/characters"] = () => json([]);
    renderApp("/works/7?tab=overview");
    const panel = await screen.findByRole("region", { name: "공개 상태" });
    expect(within(panel).getByRole("button", { name: "공개하기" })).toBeDisabled();
    expect(within(panel).getByText("확정된 버전이 없어 공개할 수 없습니다.")).toBeInTheDocument();
  });

  it("관리자가 비공개한 작품은 제작자에게 공개 버튼이 없다", async () => {
    routes["GET /api/works/7"] = () => json({ ...work, 공개권한: "관리자" });
    routes["GET /api/works/7/characters"] = () => json([]);
    renderApp("/works/7?tab=overview");
    const panel = await screen.findByRole("region", { name: "공개 상태" });
    expect(within(panel).getByText(/관리자가 비공개 처리했습니다/)).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "공개하기" })).not.toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: /돌려주기/ })).not.toBeInTheDocument();
  });

  it("관리자 권한이 있어도 자기 작품은 제작자 자격이라 관리자가 비공개한 작품을 공개할 수 없다", async () => {
    routes["GET /api/auth/me"] = () => json({ ...account, 권한: "관리자" });
    routes["GET /api/works/7"] = () => json({ ...work, 공개권한: "관리자" });
    routes["GET /api/works/7/characters"] = () => json([]);
    renderApp("/works/7?tab=overview");
    const panel = await screen.findByRole("region", { name: "공개 상태" });
    expect(within(panel).queryByRole("button", { name: "공개하기" })).not.toBeInTheDocument();
  });

  it("운영자는 자기 작품에서 운영자가 비공개한 작품을 공개하거나 제작자에게 돌려줄 수 있다", async () => {
    routes["GET /api/auth/me"] = () => json({ ...account, 권한: "운영자" });
    routes["GET /api/works/7"] = () => json({ ...work, 공개권한: "운영자" });
    routes["GET /api/works/7/characters"] = () => json([]);
    renderApp("/works/7?tab=overview");
    const panel = await screen.findByRole("region", { name: "공개 상태" });
    expect(within(panel).getByRole("button", { name: "공개하기" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "제작자에게 공개 권한 돌려주기" })).toBeInTheDocument();
  });

  it("서버가 공개를 거부하면 사유를 보여 준다", async () => {
    routes["GET /api/works/7"] = () => json(work);
    routes["GET /api/works/7/characters"] = () => json([]);
    routes["POST /api/works/7/publish"] = () => json({ detail: "이 작품에 대한 권한이 없습니다" }, 403);
    renderApp("/works/7?tab=overview");
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
    renderApp("/works/7?tab=overview");
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
    renderApp("/works/7?tab=overview");
    const panel = await screen.findByRole("region", { name: "테스터" });
    await userEvent.type(within(panel).getByLabelText("테스터 아이디"), "nobody");
    await userEvent.click(within(panel).getByRole("button", { name: "추가" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent("해당 아이디의 계정이 없습니다");
  });

  it("남이 테스터로 지정해 준 비공개 작품을 목록 아래에 보여 준다 (내 작품은 중복 표시하지 않는다)", async () => {
    routes["GET /api/works"] = () => json([work]);
    routes["GET /api/private-play-works"] = () => json([
      { 번호: 7, 제목: "저택의 비밀", 시놉시스: "", 장르: "추리", 최소인원: 1, 최대인원: 1, 예상시간: "3시간" },
      { 번호: 8, 제목: "남의 작품", 시놉시스: "", 장르: "", 최소인원: 2, 최대인원: 4, 예상시간: "2시간" },
    ]);
    renderApp();
    expect(await screen.findByText("비공개 플레이 작품")).toBeInTheDocument();
    expect(screen.getByText("남의 작품")).toBeInTheDocument();
    expect(screen.getAllByText("저택의 비밀")).toHaveLength(1);
  });

  it("서버가 거부하면 기본정보 저장 오류를 보여 준다", async () => {
    routes["GET /api/works/7"] = () => json(work);
    routes["GET /api/works/7/characters"] = () => json([]);
    routes["PATCH /api/works/7"] = () => json({ detail: "최소인원은 현재 인원(1명)보다 클 수 없습니다. 인물을 먼저 추가해 주세요" }, 409);
    renderApp("/works/7?tab=overview");
    const form = await screen.findByRole("form", { name: "기본정보" });
    const min = within(form).getByLabelText("최소 인원");
    await userEvent.clear(min);
    await userEvent.type(min, "4");
    await userEvent.click(within(form).getByRole("button", { name: "저장" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("최소인원은 현재 인원(1명)보다 클 수 없습니다");
  });

  it("없는 작품이면 오류와 목록 링크를 보여 준다", async () => {
    routes["GET /api/works/99"] = () => json({ detail: "작품을 찾을 수 없습니다" }, 404);
    routes["GET /api/works/99/characters"] = () => json({ detail: "작품을 찾을 수 없습니다" }, 404);
    renderApp("/works/99?tab=overview");
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
    expect(await calls.find((c) => c.key === "POST /api/rooms/join")!.req.json()).toEqual({ 입장코드: "K7M2QX" });
    expect(screen.getByRole("button", { name: "나가기" })).toBeInTheDocument();
  });

  it("입장코드가 틀리거나 너무 많이 틀리면 서버 메시지를 보여 준다", async () => {
    routes["POST /api/rooms/join"] = () => json({ detail: "입장코드가 올바르지 않습니다" }, 404);
    renderApp("/rooms/join");
    await userEvent.type(await screen.findByLabelText("입장코드"), "ZZZZZZ");
    await userEvent.click(screen.getByRole("button", { name: "입장하기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("입장코드가 올바르지 않습니다");
  });

  it("방 만들기: 방장 참여를 끄고 만들면 그 값을 보내고 대기실로 간다", async () => {
    let inRoom = false;
    routes["GET /api/rooms/me"] = () => json(inRoom ? baseRoom : null);
    routes["POST /api/rooms"] = () => {
      inRoom = true;
      return json(baseRoom, 201);
    };
    renderApp("/rooms/new/7");
    await userEvent.click(await screen.findByLabelText("나도 플레이어로 참여"));
    await userEvent.click(screen.getByRole("button", { name: "방 만들기" }));
    expect(await screen.findByRole("heading", { name: "저택의 비밀" })).toBeInTheDocument();
    expect(await calls.find((c) => c.key === "POST /api/rooms")!.req.json()).toEqual({ 작품_번호: 7, 방장_참여: false });
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
    renderApp("/works/7?tab=overview");
    const panel = await screen.findByRole("region", { name: "방" });
    expect(within(panel).getByRole("button", { name: "방 만들기" })).toBeDisabled();
    expect(within(panel).getByText("확정된 버전이 없어 방을 만들 수 없습니다.")).toBeInTheDocument();
  });

  it("작품 상세에서 확정 버전이 있으면 방 만들기로 이동할 수 있다", async () => {
    routes["GET /api/works/7"] = () => json(work);
    routes["GET /api/works/7/characters"] = () => json([]);
    routes["GET /api/works/7/testers"] = () => json([]);
    renderApp("/works/7?tab=overview");
    const panel = await screen.findByRole("region", { name: "방" });
    expect(within(panel).getByRole("link", { name: "이 작품으로 방 만들기" })).toHaveAttribute("href", "/rooms/new/7");
  });

  it("관리자가 비공개한 작품은 제작자에게 방 만들기를 막는다", async () => {
    routes["GET /api/works/7"] = () => json({ ...work, 공개권한: "관리자" });
    routes["GET /api/works/7/characters"] = () => json([]);
    routes["GET /api/works/7/testers"] = () => json([]);
    renderApp("/works/7?tab=overview");
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
    vi.spyOn(window, "confirm").mockReturnValue(true);
    let open = true;
    routes["GET /api/rooms/me"] = () => json(open ? baseRoom : null);
    routes["POST /api/rooms/leave"] = () => {
      open = false;
      return new Response(null, { status: 204 });
    };
    renderApp("/room");
    await userEvent.click(await screen.findByRole("button", { name: "방 닫기" }));
    expect(await screen.findByRole("heading", { name: "내 작품" })).toBeInTheDocument();
    expect(calls.map((c) => c.key)).toContain("POST /api/rooms/leave");
  });

  it("확인을 취소하면 방을 닫지 않는다", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    routes["GET /api/rooms/me"] = () => json(baseRoom);
    renderApp("/room");
    await userEvent.click(await screen.findByRole("button", { name: "방 닫기" }));
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

  it("테스터로 지정된 작품 카드에서 비공개 플레이 방을 만들 수 있다", async () => {
    routes["GET /api/private-play-works"] = () => json([
      { 번호: 8, 제목: "남의 작품", 시놉시스: "", 장르: "", 최소인원: 2, 최대인원: 4, 예상시간: "2시간" },
    ]);
    renderApp();
    const link = await screen.findByRole("link", { name: "비공개 플레이 방 만들기" });
    expect(link).toHaveAttribute("href", "/rooms/new/8");
  });
});
