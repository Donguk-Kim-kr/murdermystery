import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    { key: "testimonies", label: "증언", key_col: "순서", title_fields: ["화자"], group_by: null, help: null, fields: [
      field("화자", "text", { required: true }), field("내용", "long", { required: true }),
    ] },
    { key: "combos", label: "조합", key_col: "순서", title_fields: ["이름"], group_by: null, help: null, fields: [field("이름", "text", { required: true })] },
    { key: "combo-parts", label: "조합 재료", key_col: "번호", title_fields: [], group_by: "결과_조합_순서", help: null, fields: [
      field("결과_조합_순서", "ref", { ref: "combos", required: true }),
    ] },
    { key: "relations", label: "관계", key_col: "번호", title_fields: [], group_by: "인물_순서", help: null, fields: [
      field("인물_순서", "ref", { ref: "characters", required: true }), field("대상_인물_순서", "ref", { ref: "characters", required: true }),
      field("관계", "text", { required: true }),
    ] },
    { key: "phases", label: "페이즈(진행 순서)", key_col: "순서", title_fields: ["이름"], group_by: null, help: null, fields: [
      field("이름", "text"), field("진행시간", "int", { required: true, default: 30 }),
    ] },
    { key: "phase-steps", label: "페이즈의 진행단계", key_col: "번호", title_fields: [], group_by: "진행순서_순서", help: null, fields: [
      field("진행순서_순서", "ref", { ref: "phases", required: true }), field("진행단계_번호", "libref", { ref: "phases", required: true }),
      field("설정", "json"),
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
  places: [], clues: [], testimonies: [], combos: [], "combo-parts": [], relations: [], phases: [], "phase-steps": [], "gimmick-uses": [], endings: [], characters: [person],
  library: { phases: {}, gimmicks: {} },
});

beforeEach(() => {
  bundle = emptyBundle();
  routes = {
    "GET /api/works/7/confirm/check": () => json({ errors: [], warnings: [], 다음버전: "1.0" }),
    "GET /api/works/7/versions": () => json([]),
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

  it("작품을 열면 게임 흐름 탭이 먼저 열린다", async () => {
    routes["GET /api/library/phases"] = () => json([]);
    routes["GET /api/library/gimmicks"] = () => json([]);
    routes["GET /api/works/7/content/votes"] = () => json([]);
    renderApp("/works/7");
    expect(await screen.findByRole("tab", { name: "흐름", selected: true })).toBeInTheDocument();
    expect(screen.getAllByRole("tab")[0]).toHaveAccessibleName("흐름");
    expect(await screen.findByRole("region", { name: "페이즈" })).toBeInTheDocument();
  });

  it("탭은 흐름·인물·확인이 먼저이고, 카드로 옮길 탭은 그 뒤에 따로 있다", async () => {
    routes["GET /api/library/phases"] = () => json([]);
    routes["GET /api/library/gimmicks"] = () => json([]);
    routes["GET /api/works/7/content/votes"] = () => json([]);
    renderApp("/works/7");
    await screen.findByRole("tab", { name: "흐름", selected: true });
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "흐름", "인물", "장소", "조사", "정리", "사건", "자료", "결말",
    ]);
    expect(screen.queryByRole("tab", { name: "개요" })).not.toBeInTheDocument();    // 개요는 정리 탭으로 합쳤다
  });

  it("인물 탭에서 관계를 설정하고, 장소 탭에는 장소만, 조사 탭에는 단서·증언·조합이 있다", async () => {
    renderApp("/works/7?tab=characters");
    expect(await screen.findByRole("region", { name: "인물 목록" })).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "관계" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "장소" }));
    expect(await screen.findByRole("region", { name: "장소" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "단서" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "조사" }));
    for (const name of ["단서", "증언", "조합"]) expect(await screen.findByRole("region", { name })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "장소" })).not.toBeInTheDocument();
  });

  it("확인 탭은 게임 흐름을 세로로 보여 주고 확정 검사를 함께 한다", async () => {
    bundle.phases = [{ 순서: 1, 이름: "도입", 진행시간: 10 }, { 순서: 2, 이름: null, 진행시간: 20 }];
    bundle["phase-steps"] = [{ 번호: 9, 진행순서_순서: 2, 진행단계_번호: 5, 설정: null, 표시이름: "조사" }];
    routes["GET /api/works/7/confirm/check"] = () => json({ errors: [], warnings: [], 다음버전: "1.0" });
    routes["GET /api/works/7/versions"] = () => json([]);
    renderApp("/works/7?tab=confirm");
    const review = within(await screen.findByRole("region", { name: "게임 흐름 세로 보기" }));
    expect(await review.findByText("1. 도입")).toBeInTheDocument();
    expect(review.getByText("2. 조사")).toBeInTheDocument();
    expect(review.getByText(/총 30분/)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "버전 1.0 확정" })).toBeInTheDocument();
  });

  it("탭을 눌러 오가고, 정리 탭에는 기본정보가 있다", async () => {
    renderApp("/works/7?tab=confirm");
    expect(await screen.findByRole("form", { name: "기본정보" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "결말" }));
    expect(await screen.findByRole("region", { name: "엔딩 분기" })).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "기본정보" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "정리" }));
    expect(await screen.findByRole("form", { name: "기본정보" })).toBeInTheDocument();
  });

  it("단서의 '관련 인물'은 이름으로 고르고, 비워 두면 null 을 보낸다", async () => {
    routes["POST /api/works/7/content/clues"] = () => json({ 순서: 1 }, 201);
    renderApp("/works/7?tab=clues");
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
  const W = 208;   // 페이즈 카드 폭(시험용 가상 배치)
  const GAP = 10;
  const rect = (left: number, top: number, width: number, height: number) =>
    ({ left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON() {} }) as DOMRect;

  beforeEach(() => {
    routes["GET /api/library/phases"] = () => json(libPhases);
    routes["GET /api/library/gimmicks"] = () => json([]);
    // jsdom 에는 배치가 없어서, 흐름 줄 안의 카드·빈자리를 왼쪽부터 차례로 늘어놓은 것으로 가정한다.
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      if (this.matches("ol.flow")) return rect(0, 80, 3000, 200);
      if (this.parentElement?.matches("ol.flow")) {
        let left = 0;
        for (const sib of Array.from(this.parentElement.children)) {
          const width = sib.matches("[data-slot]") ? (sib.classList.contains("wide") ? W : 56) : sib.matches("[data-tile]") ? W : 0;
          if (sib === this) return rect(left, 100, width, 150);
          left += width + GAP;
        }
      }
      return rect(0, 0, 0, 0);
    });
  });

  /** 눌러서 끌기: 포인터를 누르고, 지나가는 점들로 옮긴 뒤, 마지막 점에서 뗀다. */
  const drag = (from: Element, path: [number, number][], release = true) => {
    fireEvent.pointerDown(from, { button: 0, isPrimary: true, pointerId: 1, clientX: 0, clientY: 0 });
    for (const [x, y] of path) fireEvent.pointerMove(window, { clientX: x, clientY: y, pointerId: 1 });
    if (release) fireEvent.pointerUp(window, { clientX: path.at(-1)![0], clientY: path.at(-1)![1], pointerId: 1 });
  };
  const tileX = (i: number) => i * (W + GAP);          // i번째(0부터) 카드의 왼쪽
  const center = (i: number): [number, number] => [tileX(i) + W / 2, 150];
  const press = (el: Element) => {                      // 움직이지 않고 누르기(클릭)
    fireEvent.pointerDown(el, { button: 0, isPrimary: true, pointerId: 1, clientX: 5, clientY: 5 });
    fireEvent.pointerUp(window, { clientX: 5, clientY: 5, pointerId: 1 });
  };
  const withTray = (steps: number[]) => localStorage.setItem("mm.tray.7", JSON.stringify({ steps, gimmicks: [] }));
  const twoPhases = () => {
    bundle.phases = [{ 순서: 1, 이름: "도입", 진행시간: 10 }, { 순서: 2, 이름: null, 진행시간: 20 }];
    (bundle.library as { phases: object }).phases = { 5: { 번호: 5, 이름: "조사", 버전: 2, 설명: "d", 삭제됨: false } };
    bundle["phase-steps"] = [
      { 번호: 9, 진행순서_순서: 1, 진행단계_번호: 5, 설정: null, 표시이름: "1차 조사" },
      { 번호: 10, 진행순서_순서: 2, 진행단계_번호: 5, 설정: { 탭유지: false, 횟수: 3 }, 표시이름: "2차 조사" },
    ];
  };
  const editor = () => within(screen.getByRole("region", { name: "페이즈 편집" }));
  const tile = (n: number) => screen.getByRole("listitem", { name: `페이즈 ${n}` });

  describe("페이즈가 없을 때", () => {
    it("처음에는 페이즈가 없고, 흐름이 맨 위, 진행카드가 그 아래에 있으며 입력 양식이나 투표는 없다", async () => {
      renderApp("/works/7?tab=phases");
      const flow = await screen.findByRole("list", { name: "게임 흐름" });
      expect(within(flow).getByText(/첫 페이즈가 만들어집니다/)).toBeInTheDocument();
      expect(flow.compareDocumentPosition(screen.getByRole("region", { name: "진행카드" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(screen.queryByRole("form", { name: "페이즈 추가" })).not.toBeInTheDocument();
      expect(screen.queryByRole("region", { name: "투표" })).not.toBeInTheDocument();
    });

    it("새 페이즈 카드를 흐름에 끌어다 놓으면 페이즈가 만들어진다", async () => {
      routes["POST /api/works/7/phases/insert"] = () => json({ phases: [{ 순서: 1, 이름: null, 진행시간: 30 }] }, 201);
      renderApp("/works/7?tab=phases");
      const card = await screen.findByLabelText("새 페이즈 카드");
      drag(card, [[100, 150]], false);
      expect(document.querySelector("[data-slot]")).not.toBeNull();            // 올려 둔 자리에 빈자리가 열린다
      fireEvent.pointerUp(window, { clientX: 100, clientY: 150 });
      await waitFor(() => expect(sent("POST /api/works/7/phases/insert")).toHaveLength(1));
      expect(await sent("POST /api/works/7/phases/insert")[0].req.json()).toEqual({ position: 1, 이름: null, 진행시간: 30 });
      expect(document.querySelector(".drag-ghost")).toBeNull();                // 놓으면 끌던 복제본이 사라진다
    });

    it("새 페이즈 카드를 누르면 맨 뒤에 추가한다", async () => {
      routes["POST /api/works/7/phases/insert"] = () => json({ phases: [] }, 201);
      renderApp("/works/7?tab=phases");
      press(await screen.findByLabelText("새 페이즈 카드"));
      await waitFor(() => expect(sent("POST /api/works/7/phases/insert")).toHaveLength(1));
      expect(await sent("POST /api/works/7/phases/insert")[0].req.json()).toEqual({ position: 1, 이름: null, 진행시간: 30 });
    });

    it("흐름 밖에서 놓으면 아무것도 하지 않는다", async () => {
      renderApp("/works/7?tab=phases");
      drag(await screen.findByLabelText("새 페이즈 카드"), [[100, 600]]);
      await new Promise((r) => setTimeout(r, 30));
      expect(calls.filter((c) => c.key.includes("/phases/"))).toHaveLength(0);
    });
  });

  describe("진행카드 불러오기", () => {
    it("라이브러리의 진행단계를 골라 진행카드로 불러오고, 이름으로 검색하며, 브라우저에 기억한다", async () => {
      renderApp("/works/7?tab=phases");
      expect(await screen.findByText(/진행카드 불러오기"로 라이브러리/)).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "진행카드 불러오기" }));
      const dialog = within(screen.getByRole("dialog", { name: "진행카드 불러오기" }));
      await userEvent.type(dialog.getByLabelText("이름 검색"), "없는이름");
      expect(dialog.getByText("찾는 이름이 없습니다.")).toBeInTheDocument();
      await userEvent.clear(dialog.getByLabelText("이름 검색"));
      const pick = dialog.getByRole("button", { name: "조사 v2" });
      expect(pick).toHaveAttribute("aria-pressed", "false");
      await userEvent.click(pick);                                                       // 눌러서 선택
      expect(pick).toHaveAttribute("aria-pressed", "true");
      expect(pick).toHaveTextContent("선택됨");
      await userEvent.keyboard("{Escape}");
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(screen.getByLabelText("진행단계 카드 조사")).toHaveTextContent("v2");
      expect(JSON.parse(localStorage.getItem("mm.tray.7")!)).toEqual({ steps: [5], gimmicks: [] });
      await userEvent.click(screen.getByRole("button", { name: "조사 v2 빼기" }));                 // 카드의 ×
      expect(screen.queryByLabelText("진행단계 카드 조사")).not.toBeInTheDocument();
    });

    it("라이브러리에 진행단계가 없으면 만들러 가는 길을 안내한다", async () => {
      routes["GET /api/library/phases"] = () => json([]);
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("button", { name: "진행카드 불러오기" }));
      expect(screen.getByRole("link", { name: "라이브러리 만들기" })).toHaveAttribute("href", "/make/library");
    });

    it("격자 카드는 이름만 보이고(같은 이름이 둘 이상일 때만 버전), 설명은 마우스를 올렸을 때 나오는 안내에 있다", async () => {
      routes["GET /api/library/phases"] = () => json([
        { 번호: 5, 이름: "조사", 버전: 2, 설명: "장소를 골라 단서를 얻는 단계", 변경내역: "시간 연장", 공통: false },
        { 번호: 4, 이름: "조사", 버전: 1, 설명: "장소를 골라 단서를 얻는 단계", 변경내역: null, 공통: false },
        { 번호: 6, 이름: "토론", 버전: 1, 설명: "모두가 이야기", 변경내역: null, 공통: false },
      ]);
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("button", { name: "진행카드 불러오기" }));
      const dialog = screen.getByRole("dialog", { name: "진행카드 불러오기" });
      const grid = within(dialog).getByRole("list");
      expect(grid).toHaveClass("loader-grid");
      const talk = within(grid).getByRole("button", { name: "토론 v1" });
      expect(talk).toHaveTextContent("토론");
      expect(talk).not.toHaveTextContent("v1");                                     // 이름만
      expect(within(grid).getByRole("button", { name: "조사 v2" })).toHaveTextContent("v2");   // 같은 이름 둘 → 버전으로 구분
            // 설명은 카드 오른쪽 위의 i 버튼으로 펼친다(마우스를 올리는 것에 기대지 않는다)
      expect(screen.queryByText(/모두가 이야기/)).not.toBeInTheDocument();
      const info = within(grid).getByRole("button", { name: "토론 v1 설명 보기" });
      expect(info).toHaveAttribute("aria-expanded", "false");
      await userEvent.click(info);
      expect(within(grid).getByRole("note")).toHaveTextContent(/v1[\s\S]*모두가 이야기/);
      expect(talk).toHaveAttribute("aria-pressed", "false");                         // 설명을 열어도 선택되지는 않는다
      await userEvent.click(within(grid).getByRole("button", { name: "조사 v2 설명 보기" }));      // 다른 카드를 열면 앞의 것은 닫힌다
      expect(within(grid).getAllByRole("note")).toHaveLength(1);
      expect(within(grid).getByRole("note")).toHaveTextContent("변경: 시간 연장");
      await userEvent.click(screen.getByLabelText("이름 검색"));                      // 다른 곳을 누르면 닫힌다
      expect(within(grid).queryByRole("note")).not.toBeInTheDocument();
    });
  });

  describe("페이즈가 둘 있을 때", () => {
    beforeEach(() => {
      twoPhases();
      withTray([5]);
    });

    it("흐름의 카드는 작은 번호(01) · 페이즈 이름 · 진행단계(버전 없이) · 시간을 보여 주고, 시간은 오른쪽에 있다", async () => {
      renderApp("/works/7?tab=phases");
      const first = await screen.findByRole("listitem", { name: "페이즈 1" });
      expect(within(first).getByText("01")).toBeInTheDocument();
      expect(within(first).getByText("도입")).toBeInTheDocument();
      expect(within(first).getByText("1차 조사")).toBeInTheDocument();          // 같은 카드가 둘이면 서버가 정한 1차·2차 이름
      expect(first).not.toHaveTextContent("v2");
      expect(first.querySelector(".tile-head")!.lastElementChild).toHaveTextContent("10분");
      const second = tile(2);
      expect(within(second).getByText("02")).toBeInTheDocument();
      expect(within(second).getByText("이름 없음")).toBeInTheDocument();
      expect(within(second).getByLabelText("세부 설정 있음")).toBeInTheDocument();
      expect(first.querySelector(".grip")).toBeNull();                          // 점 여섯 개 손잡이는 없다
      expect(screen.queryByRole("button", { name: /편집$/ })).not.toBeInTheDocument();
    });

    it("처음에는 수정 패널이 닫혀 있고, 카드를 한 번 누르면 그 페이즈가 열린다", async () => {
      renderApp("/works/7?tab=phases");
      await screen.findByRole("listitem", { name: "페이즈 1" });
      expect(screen.queryByRole("region", { name: "페이즈 편집" })).not.toBeInTheDocument();
      await userEvent.click(tile(2));
      expect(screen.getByRole("heading", { name: "02 페이즈 편집" })).toBeInTheDocument();
      expect(editor().getByText("2차 조사 v2")).toBeInTheDocument();
      await userEvent.click(editor().getByRole("button", { name: "닫기" }));
      expect(screen.queryByRole("region", { name: "페이즈 편집" })).not.toBeInTheDocument();
    });

    it("진행카드를 페이즈 가운데에 놓으면 그 페이즈에 붙고, 올려 둔 페이즈가 강조된다", async () => {
      routes["POST /api/works/7/content/phase-steps"] = () => json({ 번호: 11 }, 201);
      renderApp("/works/7?tab=phases");
      const card = await screen.findByLabelText("진행단계 카드 조사");
      drag(card, [center(1)], false);
      expect(tile(2).className).toContain("over");
      expect(document.querySelector(".drag-ghost")).not.toBeNull();             // 카드 자체(복제본)가 포인터를 따라간다
      fireEvent.pointerUp(window, { clientX: center(1)[0], clientY: 150 });
      await waitFor(() => expect(sent("POST /api/works/7/content/phase-steps")).toHaveLength(1));
      expect(await sent("POST /api/works/7/content/phase-steps")[0].req.json()).toEqual({ 진행순서_순서: 2, 진행단계_번호: 5 });
      expect(screen.queryByText(/여기에 놓기/)).not.toBeInTheDocument();
    });

    it("진행카드를 페이즈 가장자리(틈)에 올리면 그 자리만 열리고, 놓으면 새 페이즈로 끼워 넣어 거기에 붙인다", async () => {
      routes["POST /api/works/7/phases/insert"] = () => json({ phases: [
        { 순서: 1, 이름: "도입", 진행시간: 10 }, { 순서: 3, 이름: null, 진행시간: 30 }, { 순서: 2, 이름: null, 진행시간: 20 },
      ] }, 201);
      routes["POST /api/works/7/content/phase-steps"] = () => json({ 번호: 11 }, 201);
      renderApp("/works/7?tab=phases");
      const card = await screen.findByLabelText("진행단계 카드 조사");
      drag(card, [[tileX(1) + 4, 150]], false);                                   // 2번째 카드의 왼쪽 가장자리
      expect(document.querySelectorAll("[data-slot]")).toHaveLength(1);           // 빈자리는 올려 둔 한 곳만 열린다
      const flow = screen.getByRole("list", { name: "게임 흐름" });
      expect([...flow.children].map((c) => c.hasAttribute("data-slot") ? "빈자리" : "카드")).toEqual(["카드", "빈자리", "카드"]);
      fireEvent.pointerUp(window, { clientX: tileX(1) + 4, clientY: 150 });
      await waitFor(() => expect(sent("POST /api/works/7/content/phase-steps")).toHaveLength(1));
      expect(await sent("POST /api/works/7/phases/insert")[0].req.json()).toEqual({ position: 2, 이름: null, 진행시간: 30 });
      expect(await sent("POST /api/works/7/content/phase-steps")[0].req.json()).toEqual({ 진행순서_순서: 3, 진행단계_번호: 5 });   // 새 칸
    });

    it("페이즈에 붙은 진행단계를 끌어 다른 페이즈에 놓으면 옮겨진다", async () => {
      routes["PATCH /api/works/7/content/phase-steps/9"] = () => json({});
      renderApp("/works/7?tab=phases");
      const chip = (await screen.findByRole("listitem", { name: "페이즈 1" })).querySelector(".chip")!;
      drag(chip, [center(1)]);
      await waitFor(() => expect(sent("PATCH /api/works/7/content/phase-steps/9")).toHaveLength(1));
      expect(await sent("PATCH /api/works/7/content/phase-steps/9")[0].req.json()).toEqual({ 진행순서_순서: 2 });
    });

    it("붙은 진행단계를 누르기만 하면 그 페이즈가 열린다(끌기와 구분)", async () => {
      renderApp("/works/7?tab=phases");
      press((await screen.findByRole("listitem", { name: "페이즈 2" })).querySelector(".chip")!);
      expect(await screen.findByRole("heading", { name: "02 페이즈 편집" })).toBeInTheDocument();
      expect(calls.filter((c) => c.key.startsWith("PATCH"))).toHaveLength(0);
    });

    it("페이즈 카드를 끌면 카드 자체가 빠져나가 따라오고, 올려 둔 자리에 폭이 같은 빈자리가 열려 순서가 바뀐다", async () => {
      routes["POST /api/works/7/phases/1/move"] = () => json({ phases: [] });
      renderApp("/works/7?tab=phases");
      const first = await screen.findByRole("listitem", { name: "페이즈 1" });
      drag(first, [[10, 150], [tileX(1) + 150, 150]], false);                    // 두 번째 카드의 오른쪽 절반 → 그 뒤
      expect(screen.queryByRole("listitem", { name: "페이즈 1" })).not.toBeInTheDocument();       // 흐름에서 빠졌다
      expect(document.querySelector(".drag-ghost")).not.toBeNull();
      const flow = screen.getByRole("list", { name: "게임 흐름" });
      expect([...flow.children].map((c) => c.hasAttribute("data-slot") ? "빈자리" : "카드")).toEqual(["카드", "빈자리"]);
      expect(flow.querySelector("[data-slot]")).toHaveClass("wide");
      fireEvent.pointerUp(window, { clientX: tileX(1) + 150, clientY: 150 });
      await waitFor(() => expect(sent("POST /api/works/7/phases/1/move")).toHaveLength(1));
      expect(await sent("POST /api/works/7/phases/1/move")[0].req.json()).toEqual({ position: 2 });
    });

    it("페이즈 카드를 제자리에 놓으면 서버에 요청하지 않는다", async () => {
      renderApp("/works/7?tab=phases");
      drag(await screen.findByRole("listitem", { name: "페이즈 1" }), [[10, 150]]);
      await new Promise((r) => setTimeout(r, 30));
      expect(calls.filter((c) => c.key.includes("/move"))).toHaveLength(0);
      expect(screen.getByRole("listitem", { name: "페이즈 1" })).toBeInTheDocument();         // 카드가 돌아온다
    });

    it("앞으로·뒤로는 위치(1부터)로 서버에 요청한다", async () => {
      routes["POST /api/works/7/phases/2/move"] = () => json({ phases: bundle.phases });
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 2" }));
      await userEvent.click(screen.getByRole("button", { name: "페이즈 2 앞으로" }));
      expect(await sent("POST /api/works/7/phases/2/move")[0].req.json()).toEqual({ position: 1 });
      expect(screen.getByRole("button", { name: "페이즈 2 뒤로" })).toBeDisabled();
    });

    it("수정 패널에서 이름·시간을 저장하고, 서버 값이 바뀌면 입력칸도 따라 바뀐다", async () => {
      routes["PATCH /api/works/7/content/phases/2"] = () => {
        bundle.phases = [{ 순서: 1, 이름: "도입", 진행시간: 10 }, { 순서: 2, 이름: "토론", 진행시간: 45 }];
        return json({});
      };
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 2" }));
      await userEvent.type(editor().getByLabelText("페이즈 이름"), "토론");
      await userEvent.clear(editor().getByLabelText("진행 시간(분)"));
      await userEvent.type(editor().getByLabelText("진행 시간(분)"), "45");
      await userEvent.click(editor().getByRole("button", { name: "이름·시간 저장" }));
      expect(await sent("PATCH /api/works/7/content/phases/2")[0].req.json()).toEqual({ 이름: "토론", 진행시간: 45 });
      const second = tile(2);
      await waitFor(() => expect(within(second).getByText("토론")).toBeInTheDocument());       // 카드에도 바로 반영
      expect(within(second).getByText("45분")).toBeInTheDocument();
    });

    it("페이즈 삭제는 확인 후 서버에 요청하고 수정 패널을 닫는다", async () => {
      routes["DELETE /api/works/7/phases/2"] = () => json({ phases: [] });
      vi.spyOn(window, "confirm").mockReturnValue(true);
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 2" }));
      await userEvent.click(screen.getByRole("button", { name: "페이즈 2 삭제" }));
      await waitFor(() => expect(sent("DELETE /api/works/7/phases/2")).toHaveLength(1));
      await waitFor(() => expect(screen.queryByRole("region", { name: "페이즈 편집" })).not.toBeInTheDocument());
    });

    it("세로로 보기는 읽기 전용 팝업으로 흐름을 위에서 아래로 보여 주고 닫을 수 있다", async () => {
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("button", { name: "세로로 보기" }));
      const dialog = within(screen.getByRole("dialog", { name: "세로로 보기" }));
      expect(dialog.getByText("1. 도입")).toBeInTheDocument();
      expect(dialog.getByText("2. 2차 조사")).toBeInTheDocument();     // 이름이 없으면 안의 카드 이름
      expect(dialog.getByText(/총 30분/)).toBeInTheDocument();
      expect(dialog.queryByRole("textbox")).not.toBeInTheDocument();    // 편집 칸 없음
      await userEvent.keyboard("{Escape}");
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("카드 설정: 탭을 남기지 않기를 고르면 설정에 담고, 기본값이면 비운다", async () => {
      routes["PATCH /api/works/7/content/phase-steps/9"] = () => json({});
      routes["PATCH /api/works/7/content/phase-steps/10"] = () => json({});
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 1" }));
      await userEvent.click(await screen.findByRole("button", { name: "1차 조사 설정" }));
      const box = within(screen.getByRole("group", { name: "세부 설정" }));
      expect(box.getByLabelText(/다음 페이즈에도 남기기/)).toBeChecked();
      await userEvent.click(box.getByLabelText(/다음 페이즈에도 남기기/));
      await userEvent.click(box.getByRole("button", { name: "설정 저장" }));
      expect(await sent("PATCH /api/works/7/content/phase-steps/9")[0].req.json()).toEqual({ 설정: { 탭유지: false } });

      await userEvent.click(tile(2));
      await userEvent.click(await screen.findByRole("button", { name: "2차 조사 설정" }));
      const second = within(screen.getByRole("group", { name: "세부 설정" }));
      expect(second.getByLabelText(/다음 페이즈에도 남기기/)).not.toBeChecked();
      expect(second.getByLabelText(/JSON/)).toHaveValue(JSON.stringify({ 횟수: 3 }, null, 2));
      await userEvent.click(second.getByLabelText(/다음 페이즈에도 남기기/));
      await userEvent.clear(second.getByLabelText(/JSON/));
      await userEvent.click(second.getByRole("button", { name: "설정 저장" }));
      expect(await sent("PATCH /api/works/7/content/phase-steps/10")[0].req.json()).toEqual({ 설정: null });
    });

    it("붙은 카드를 설정째로 다른 페이즈에 복사한다(같은 진행단계가 이미 있는 페이즈는 뺀다)", async () => {
      routes["POST /api/works/7/content/phase-steps"] = () => json({ 번호: 11 }, 201);
      bundle.phases = [{ 순서: 1, 이름: "도입", 진행시간: 10 }, { 순서: 2, 이름: null, 진행시간: 20 }, { 순서: 3, 이름: "결말", 진행시간: 5 }];
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 2" }));
      await userEvent.click(editor().getByRole("button", { name: "2차 조사 복사" }));
      const box = within(screen.getByRole("group", { name: "복사" }));
      expect(box.getAllByRole("option").map((o) => o.textContent)).toEqual(["고르기…", "3. 결말"]);
      await userEvent.selectOptions(box.getByRole("combobox"), "3");
      await userEvent.click(box.getByRole("button", { name: "복사" }));
      expect(await sent("POST /api/works/7/content/phase-steps")[0].req.json()).toEqual({
        진행순서_순서: 3, 진행단계_번호: 5, 설정: { 탭유지: false, 횟수: 3 },
      });
    });

    it("JSON 이 객체가 아니면 저장하지 않는다", async () => {
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 1" }));
      await userEvent.click(await screen.findByRole("button", { name: "1차 조사 설정" }));
      const box = within(screen.getByRole("group", { name: "세부 설정" }));
      await userEvent.type(box.getByLabelText(/JSON/), "[[1]");   // "[[" 는 글자 "[" 이다
      await userEvent.click(box.getByRole("button", { name: "설정 저장" }));
      expect(await box.findByRole("alert")).toHaveTextContent("JSON 객체");
      expect(sent("PATCH /api/works/7/content/phase-steps/9")).toHaveLength(0);
    });
  });

  it("삭제된 라이브러리 항목은 '삭제된 항목'으로 표시한다", async () => {
    bundle.phases = [{ 순서: 1, 이름: null, 진행시간: 30 }];
    bundle["phase-steps"] = [{ 번호: 9, 진행순서_순서: 1, 진행단계_번호: 5, 설정: null, 표시이름: "옛 조사" }];
    (bundle.library as { phases: object }).phases = { 5: { 번호: 5, 이름: "옛 조사", 버전: 1, 설명: "", 삭제됨: true } };
    renderApp("/works/7?tab=phases");
    const chip = within(await screen.findByRole("listitem", { name: "페이즈 1" })).getByText(/옛 조사/);
    expect(chip).toHaveTextContent("삭제된 항목");
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

describe("개요·인물 탭", () => {
  it("제목은 나중에 바꿀 수 있다고 안내한다", async () => {
    renderApp("/works/7?tab=confirm");
    expect(await screen.findByText(/제목은 임시로 정해도 됩니다/)).toBeInTheDocument();
  });

  it("인물 이름은 나중에 바꿀 수 있다고 안내한다", async () => {
    renderApp("/works/7?tab=characters");
    await userEvent.click(await screen.findByRole("button", { name: "인물 추가" }));
    expect(screen.getByText(/이름은 임시로 정해도 됩니다/)).toBeInTheDocument();
  });

  it("인물을 삭제하면 확인 후 서버에 알리고, 거부되면 사유를 보여 준다", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    routes["DELETE /api/works/7/characters/1"] = () => json({ detail: "다른 항목이 이 인물을 사용하고 있어 지울 수 없습니다" }, 409);
    renderApp("/works/7?tab=characters");
    await userEvent.click(await screen.findByRole("button", { name: "삭제" }));
    expect(await screen.findByText(/다른 항목이 이 인물을 사용하고 있어/)).toBeInTheDocument();
  });
});

describe("작품 제목 바로 고치기", () => {
  beforeEach(() => {
    routes["GET /api/library/phases"] = () => json([]);
    routes["GET /api/library/gimmicks"] = () => json([]);
    routes["GET /api/works/7/content/votes"] = () => json([]);
  });

  it("머리글의 제목을 고치고 Enter 를 누르면 저장한다", async () => {
    routes["PATCH /api/works/7"] = () => json({ ...work, 제목: "새 제목" });
    renderApp("/works/7");
    const title = await screen.findByRole("textbox", { name: "작품 제목" });
    expect(title).toHaveValue("저택의 비밀");
    await userEvent.clear(title);
    await userEvent.type(title, "새 제목{Enter}");
    await waitFor(() => expect(sent("PATCH /api/works/7")).toHaveLength(1));
    expect(await sent("PATCH /api/works/7")[0].req.json()).toEqual({ 제목: "새 제목" });
  });

  it("다른 곳을 눌러 포커스가 벗어나도 저장하고, 바뀌지 않았으면 보내지 않는다", async () => {
    routes["PATCH /api/works/7"] = () => json({ ...work, 제목: "바뀐 제목" });
    renderApp("/works/7");
    const title = await screen.findByRole("textbox", { name: "작품 제목" });
    await userEvent.click(title);
    await userEvent.tab();                                                   // 그대로 벗어남
    expect(sent("PATCH /api/works/7")).toHaveLength(0);
    await userEvent.clear(title);
    await userEvent.type(title, "바뀐 제목");
    await userEvent.tab();
    await waitFor(() => expect(sent("PATCH /api/works/7")).toHaveLength(1));
  });

  it("Esc 는 취소하고, 비운 채로는 저장하지 않고 이전 제목으로 되돌린다", async () => {
    renderApp("/works/7");
    const title = await screen.findByRole("textbox", { name: "작품 제목" });
    await userEvent.clear(title);
    await userEvent.type(title, "취소할 제목{Escape}");
    expect(title).toHaveValue("저택의 비밀");
    await userEvent.clear(title);
    await userEvent.tab();
    expect(title).toHaveValue("저택의 비밀");
    expect(sent("PATCH /api/works/7")).toHaveLength(0);
  });

  it("서버가 거부하면 사유를 보여 주고 이전 제목으로 되돌린다", async () => {
    routes["PATCH /api/works/7"] = () => json({ detail: "제목을 저장하지 못했습니다" }, 409);
    renderApp("/works/7");
    const title = await screen.findByRole("textbox", { name: "작품 제목" });
    await userEvent.clear(title);
    await userEvent.type(title, "안 되는 제목{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("제목을 저장하지 못했습니다");
    expect(title).toHaveValue("저택의 비밀");
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
    renderApp("/make/library");
    const lineage = await screen.findByRole("listitem", { name: "진행단계 나만의 조사" });
    expect(within(lineage).getByText("v2")).toBeInTheDocument();
    expect(within(lineage).getByText("변경: 시간 연장")).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "진행단계 토론" })).toHaveTextContent("공통");
  });

  it("일반 사용자에게는 공통 항목 버튼이 없고 이름 변경은 계열 전체로 보낸다", async () => {
    routes["PATCH /api/library/phases/2"] = () => json(item({ 이름: "새 이름" }));
    renderApp("/make/library");
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
    renderApp("/make/library");
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
    renderApp("/make/library");
    expect((await screen.findAllByLabelText(/공통 항목으로 만들기/)).length).toBeGreaterThan(0);
  });
});
