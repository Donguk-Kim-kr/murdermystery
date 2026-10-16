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

const account = { 번호: 1, 아이디: "alice", 닉네임: "탐정", 권한: "사용자" };
const work = {
  번호: 7, 제목: "저택의 비밀", 시놉시스: "", 장르: "", 최소인원: 1, 최대인원: 1, 예상시간: "3시간", 상태: "개발",
  공개여부: false, 공개권한: "제작자", 확정버전_있음: false, 생성일시: "2026-10-14T00:00:00Z", 수정일시: null, 공통스토리: null,
};
const person = { 순서: 1, 이름: "홍길동", 직업: null, 나이: null, 성별: null, 서사: "", 타임라인: null, 능력: null, 비밀: null, 목표: null, 범인: false, NPC: false };

const field = (name: string, kind: string, extra: Record<string, unknown> = {}) => ({
  name, kind, required: false, max: null, min: null, ref: null, label: name, help: null, default: null, ...extra,
});
const schema = {
  resources: [
    { key: "places", label: "장소", key_col: "순서", title_fields: ["이름"], group_by: null, help: null, fields: [
      field("이름", "text", { required: true, help: "나중에 바꿀 수 있습니다" }), field("유형", "text"),
      field("상위_장소_순서", "ref", { ref: "places", label: "상위 장소" }),
    ] },
    { key: "clues", label: "단서", key_col: "순서", title_fields: ["이름"], group_by: null, help: null, fields: [
      field("이름", "text", { required: true }), field("인물_순서", "ref", { ref: "characters", label: "관련 인물" }),
    ] },
    { key: "phases", label: "페이즈(진행 순서)", key_col: "순서", title_fields: [], group_by: null, help: null, fields: [
      field("진행시간", "int", { required: true, default: 30 }),
    ] },
    { key: "phase-steps", label: "페이즈의 진행단계", key_col: "번호", title_fields: [], group_by: "진행순서_순서", help: null, fields: [
      field("진행순서_순서", "ref", { ref: "phases", required: true }), field("진행단계_번호", "libref", { ref: "phases", required: true }),
    ] },
    { key: "gimmick-uses", label: "페이즈에 붙은 기믹", key_col: "순서", title_fields: [], group_by: "진행순서_순서", help: null, fields: [
      field("기믹_번호", "libref", { ref: "gimmicks", required: true }), field("진행순서_순서", "ref", { ref: "phases", required: true }),
    ] },
    { key: "endings", label: "엔딩 분기", key_col: "순서", title_fields: ["이름", "내용"], group_by: null, help: null, fields: [
      field("이름", "text", { required: true }), field("조건", "json", { required: true, default: {} }), field("내용", "long", { required: true }),
    ] },
  ],
  external: [{ key: "characters", label: "인물", key_col: "순서", title_fields: ["이름"], external: true }],
};
let bundle: Record<string, unknown>;
const emptyBundle = () => ({
  places: [], clues: [], phases: [], "phase-steps": [], "gimmick-uses": [], endings: [], characters: [person],
  library: { phases: {}, gimmicks: {} },
});

beforeEach(() => {
  bundle = emptyBundle();
  routes = {
    "GET /api/works": () => json([]),
    "GET /api/private-play-works": () => json([]),
    "GET /api/rooms/me": () => json(null),
    "GET /api/auth/me": () => json(account),
    "GET /api/works/7": () => json(work),
    "GET /api/works/7/characters": () => json([person]),
    "GET /api/works/7/testers": () => json([]),
    "GET /api/content/schema": () => json(schema),
    "GET /api/works/7/content": () => json(bundle),
  };
  calls.length = 0;
  localStorage.clear();
  localStorage.setItem("mm.token", "saved");
  vi.stubGlobal("fetch", async (input: Request) => {
    const key = `${input.method} ${new URL(input.url).pathname}`;
    calls.push({ key, req: input.clone() });
    const handler = routes[key];
    if (!handler) throw new Error(`mock 없는 요청: ${key}`);
    return handler(input);
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const renderApp = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );

const sent = (key: string) => calls.filter((c) => c.key === key);

describe("작업공간 탭", () => {
  it("어느 탭부터 열어도 된다: 인물이 없어도 장소부터 만든다", async () => {
    bundle.characters = [];
    routes["POST /api/works/7/content/places"] = () => {
      bundle.places = [{ 순서: 1, 상위_장소_순서: null, 이름: "서재", 유형: null }];
      return json(bundle.places, 201);
    };
    renderApp("/works/7?tab=places");
    expect((await screen.findAllByText("아직 없습니다.")).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: "장소 추가" }));
    const form = screen.getByRole("form", { name: "장소 추가" });
    await userEvent.type(within(form).getByLabelText("이름"), "서재");
    expect(within(form).getByText("나중에 바꿀 수 있습니다")).toBeInTheDocument();
    await userEvent.click(within(form).getByRole("button", { name: "저장" }));
    expect(await screen.findByText("서재")).toBeInTheDocument();
    expect(await sent("POST /api/works/7/content/places")[0].req.json()).toEqual({ 이름: "서재", 유형: null, 상위_장소_순서: null });
  });

  it("탭을 눌러 오가고, 개요에는 기존 화면이 그대로 있다", async () => {
    renderApp("/works/7");
    expect(await screen.findByRole("form", { name: "기본정보" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "결말" }));
    expect(await screen.findByRole("region", { name: "엔딩 분기" })).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "기본정보" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "개요" }));
    expect(await screen.findByRole("form", { name: "기본정보" })).toBeInTheDocument();
  });

  it("단서의 '관련 인물'은 이름으로 고르고, 비워 두면 null 을 보낸다", async () => {
    routes["POST /api/works/7/content/clues"] = () => json({ 순서: 1 }, 201);
    renderApp("/works/7?tab=places");
    await userEvent.click(await screen.findByRole("button", { name: "단서 추가" }));
    const form = screen.getByRole("form", { name: "단서 추가" });
    await userEvent.type(within(form).getByLabelText("이름"), "편지");
    expect(within(form).getByRole("option", { name: "1. 홍길동" })).toBeInTheDocument();
    await userEvent.selectOptions(within(form).getByLabelText("관련 인물"), "1");
    await userEvent.click(within(form).getByRole("button", { name: "저장" }));
    await waitFor(() => expect(sent("POST /api/works/7/content/clues")).toHaveLength(1));
    expect(await sent("POST /api/works/7/content/clues")[0].req.json()).toEqual({ 이름: "편지", 인물_순서: 1 });
  });

  it("JSON 칸이 잘못되면 보내지 않고 안내한다, 서버 오류는 그대로 보여 준다", async () => {
    routes["POST /api/works/7/content/endings"] = () => json({ detail: "내용: 비울 수 없는 항목입니다" }, 422);
    renderApp("/works/7?tab=endings");
    await userEvent.click(await screen.findByRole("button", { name: "엔딩 분기 추가" }));
    const form = screen.getByRole("form", { name: "엔딩 분기 추가" });
    const cond = within(form).getByLabelText("조건");
    await userEvent.clear(cond);
    await userEvent.type(cond, "not json");
    await userEvent.click(within(form).getByRole("button", { name: "저장" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("JSON 형식");
    expect(sent("POST /api/works/7/content/endings")).toHaveLength(0);
    await userEvent.clear(cond);
    await userEvent.type(cond, "{{}");
    await userEvent.click(within(form).getByRole("button", { name: "저장" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("내용: 비울 수 없는 항목입니다");
  });

  it("항목을 삭제하면 확인 후 서버에 알린다", async () => {
    bundle.places = [{ 순서: 3, 상위_장소_순서: null, 이름: "지하실", 유형: null }];
    routes["DELETE /api/works/7/content/places/3"] = () => {
      bundle.places = [];
      return new Response(null, { status: 204 });
    };
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderApp("/works/7?tab=places");
    expect(await screen.findByText("지하실")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "삭제" }));
    await waitFor(() => expect(screen.queryByText("지하실")).not.toBeInTheDocument());
    expect(sent("DELETE /api/works/7/content/places/3")).toHaveLength(1);
  });
});

describe("진행 탭", () => {
  const libPhases = [{ 번호: 5, 이름: "조사", 버전: 2, 설명: "d", 변경내역: "시간 연장", 공통: true }];
  beforeEach(() => {
    routes["GET /api/library/phases"] = () => json(libPhases);
    routes["GET /api/library/gimmicks"] = () => json([]);
  });

  it("페이즈를 만들고 진행단계를 변경내역과 함께 골라 붙인다", async () => {
    routes["POST /api/works/7/content/phases"] = () => {
      bundle.phases = [{ 순서: 1, 진행시간: 30 }];
      return json({ 순서: 1, 진행시간: 30 }, 201);
    };
    routes["POST /api/works/7/content/phase-steps"] = () => {
      bundle["phase-steps"] = [{ 번호: 9, 진행순서_순서: 1, 진행단계_번호: 5 }];
      (bundle.library as { phases: object }).phases = { 5: { 번호: 5, 이름: "조사", 버전: 2, 설명: "d", 삭제됨: false } };
      return json({ 번호: 9 }, 201);
    };
    routes["GET /api/works/7/content/votes"] = () => json([]);
    renderApp("/works/7?tab=phases");
    await userEvent.click(await screen.findByRole("button", { name: "페이즈 추가" }));
    expect(await sent("POST /api/works/7/content/phases")[0].req.json()).toEqual({ 진행시간: 30 });
    const group = await screen.findByRole("group", { name: "페이즈 1 진행단계" });
    expect(within(group).getByRole("option", { name: "조사 v2 — 시간 연장 (공통)" })).toBeInTheDocument();
    await userEvent.selectOptions(within(group).getByLabelText("진행단계 선택"), "5");
    await userEvent.click(within(group).getByRole("button", { name: "붙이기" }));
    expect(await within(group).findByText("조사 v2")).toBeInTheDocument();
    expect(await sent("POST /api/works/7/content/phase-steps")[0].req.json()).toEqual({ 진행순서_순서: 1, 진행단계_번호: 5 });
  });

  it("삭제된 라이브러리 항목은 '삭제된 항목'으로 표시한다", async () => {
    bundle.phases = [{ 순서: 1, 진행시간: 30 }];
    bundle["phase-steps"] = [{ 번호: 9, 진행순서_순서: 1, 진행단계_번호: 5 }];
    (bundle.library as { phases: object }).phases = { 5: { 번호: 5, 이름: "옛 조사", 버전: 1, 설명: "", 삭제됨: true } };
    renderApp("/works/7?tab=phases");
    expect(await screen.findByText(/옛 조사 v1/)).toHaveTextContent("삭제된 항목");
  });
});

describe("확정 탭", () => {
  it("오류가 있으면 확정할 수 없고 이유를 보여 준다", async () => {
    routes["GET /api/works/7/confirm/check"] = () => json({ errors: ["페이즈가 없습니다."], warnings: ["범인 없음"], 다음버전: "1.0" });
    routes["GET /api/works/7/versions"] = () => json([]);
    renderApp("/works/7?tab=confirm");
    expect(await screen.findByText("페이즈가 없습니다.")).toBeInTheDocument();
    expect(screen.getByText("범인 없음")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "버전 1.0 확정" })).toBeDisabled();
  });

  it("확정하면 변경사항과 함께 보내고 버전 목록을 갱신한다", async () => {
    let versions: unknown[] = [];
    routes["GET /api/works/7/confirm/check"] = () => json({ errors: [], warnings: [], 다음버전: "1.0" });
    routes["GET /api/works/7/versions"] = () => json(versions);
    routes["POST /api/works/7/confirm"] = () => {
      versions = [{ 번호: 1, 버전: "1.0", 생성일시: "2026-10-15T00:00:00Z", 변경사항: "처음" }];
      return json(versions[0], 201);
    };
    renderApp("/works/7?tab=confirm");
    await userEvent.type(await screen.findByLabelText("변경사항 (선택)"), "처음");
    await userEvent.click(screen.getByRole("button", { name: "버전 1.0 확정" }));
    expect(await screen.findByRole("status")).toHaveTextContent("버전 1.0");
    expect(await sent("POST /api/works/7/confirm")[0].req.json()).toEqual({ 변경사항: "처음" });
    expect(within(screen.getByRole("region", { name: "확정된 버전" })).getByText("처음")).toBeInTheDocument();
  });
});

describe("개요 탭", () => {
  it("제목과 인물 이름은 나중에 바꿀 수 있다고 안내한다", async () => {
    renderApp("/works/7");
    expect(await screen.findByText(/제목은 임시로 정해도 됩니다/)).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "인물 추가" }));
    expect(screen.getByText(/이름은 임시로 정해도 됩니다/)).toBeInTheDocument();
  });

  it("인물을 삭제하면 확인 후 서버에 알리고, 거부되면 사유를 보여 준다", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    routes["DELETE /api/works/7/characters/1"] = () => json({ detail: "다른 항목이 이 인물을 사용하고 있어 지울 수 없습니다" }, 409);
    renderApp("/works/7");
    await userEvent.click(await screen.findByRole("button", { name: "삭제" }));
    expect(await screen.findByText(/다른 항목이 이 인물을 사용하고 있어/)).toBeInTheDocument();
  });
});

describe("라이브러리", () => {
  const item = (o: Record<string, unknown>) => ({
    번호: 1, 이름: "나만의 조사", 버전: 1, 설명: "d", 변경내역: null, 삭제일시: null, 공개여부: false, 공통: false, 규칙: {}, ...o,
  });
  beforeEach(() => {
    routes["GET /api/library/phases"] = () => json([item({ 번호: 2, 버전: 2, 변경내역: "시간 연장" }), item({}), item({ 번호: 3, 이름: "토론", 공통: true })]);
    routes["GET /api/library/gimmicks"] = () => json([]);
  });

  it("계열별로 묶어 버전과 변경내역을 보여 준다", async () => {
    renderApp("/library");
    const lineage = await screen.findByRole("listitem", { name: "진행단계 나만의 조사" });
    expect(within(lineage).getByText("v2")).toBeInTheDocument();
    expect(within(lineage).getByText("변경: 시간 연장")).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "진행단계 토론" })).toHaveTextContent("공통");
  });

  it("일반 사용자에게는 공통 항목 버튼이 없고 이름 변경은 계열 전체로 보낸다", async () => {
    routes["PATCH /api/library/phases/2"] = () => json(item({ 이름: "새 이름" }));
    renderApp("/library");
    const lineage = await screen.findByRole("listitem", { name: "진행단계 나만의 조사" });
    expect(screen.queryByLabelText(/공통 항목으로 만들기/)).not.toBeInTheDocument();
    // 공통 항목은 변경 버튼이 없다
    expect(within(screen.getByRole("listitem", { name: "진행단계 토론" })).queryByRole("button", { name: "이름 바꾸기" })).not.toBeInTheDocument();
    await userEvent.click(within(lineage).getByRole("button", { name: "이름 바꾸기" }));
    const input = within(lineage).getByLabelText("새 이름");
    await userEvent.clear(input);
    await userEvent.type(input, "새 이름");
    await userEvent.click(within(lineage).getByRole("button", { name: "이름 바꾸기" }));
    await waitFor(() => expect(sent("PATCH /api/library/phases/2")).toHaveLength(1));
    expect(await sent("PATCH /api/library/phases/2")[0].req.json()).toEqual({ 이름: "새 이름" });
  });

  it("만들기: 같은 이름이면 새 버전, 내용은 JSON 으로 보낸다", async () => {
    routes["POST /api/library/phases"] = () => json(item({ 버전: 3 }), 201);
    renderApp("/library");
    const form = await screen.findByRole("form", { name: "진행단계 만들기" });
    await userEvent.type(within(form).getByLabelText("이름"), "나만의 조사");
    const rule = within(form).getByLabelText("규칙 (JSON)");
    await userEvent.clear(rule);
    await userEvent.type(rule, '{{"시간": 900}');
    await userEvent.click(within(form).getByRole("button", { name: "만들기" }));
    await waitFor(() => expect(sent("POST /api/library/phases")).toHaveLength(1));
    expect(await sent("POST /api/library/phases")[0].req.json()).toEqual({
      이름: "나만의 조사", 설명: "", 변경내역: "", 공통: false, 규칙: { 시간: 900 },
    });
  });

  it("운영자에게는 '공통 항목으로 만들기' 선택이 보인다", async () => {
    routes["GET /api/auth/me"] = () => json({ ...account, 권한: "운영자" });
    renderApp("/library");
    expect((await screen.findAllByLabelText(/공통 항목으로 만들기/)).length).toBeGreaterThan(0);
  });
});
