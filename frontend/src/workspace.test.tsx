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
      field("이름", "text", { required: true }), field("공개이름", "text"), field("인물_순서", "ref", { ref: "characters", label: "관련 인물" }),
    ] },
    { key: "testimonies", label: "증언", key_col: "순서", title_fields: ["이름"], group_by: null, help: null, fields: [
      field("이름", "text", { required: true }), field("공개이름", "text"), field("내용", "long", { required: true }),
    ] },
    { key: "combos", label: "조합", key_col: "순서", title_fields: ["이름"], group_by: null, help: null, has_parts: true, fields: [field("이름", "text", { required: true })] },
    { key: "combo-parts", label: "조합 재료", key_col: "번호", title_fields: [], group_by: "결과_조합_순서", help: null, hidden: true, fields: [
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
    expect(screen.queryByRole("region", { name: "조합 재료" })).not.toBeInTheDocument();        // 재료는 조합 입력 화면에 합쳐져 있다
  });

  it("조합은 재료를 단서·증언·조합 버튼으로 골라 한 번에 저장하고, 같은 재료는 한 번만 들어간다", async () => {
    bundle.clues = [{ 순서: 1, 이름: "커터칼", 공개이름: "A의 서랍" }];
    bundle.testimonies = [{ 순서: 1, 이름: "A의 마약소문", 공개이름: "지나가던 사람", 내용: "들었습니다" }];
    bundle.combos = [{ 순서: 1, 이름: "안쪽", 재료: [] }];
    routes["POST /api/works/7/content/combos"] = () => json({ 순서: 2 }, 201);
    renderApp("/works/7?tab=clues");
    const section = within(await screen.findByRole("region", { name: "조합" }));
    await userEvent.click(section.getByRole("button", { name: "조합 추가" }));
    const form = within(section.getByRole("form", { name: "조합 추가" }));
    await userEvent.type(form.getByLabelText("이름"), "완성");
    await userEvent.click(form.getByRole("button", { name: "단서 넣기" }));
    await userEvent.selectOptions(form.getByLabelText("넣을 단서"), "1");
    expect(form.queryByRole("option", { name: /커터칼/ })).not.toBeInTheDocument();             // 이미 넣은 재료는 다시 고를 수 없다
    await userEvent.click(form.getByRole("button", { name: "증언 넣기" }));
    await userEvent.selectOptions(form.getByLabelText("넣을 증언"), "1");
    await userEvent.click(form.getByRole("button", { name: "조합 넣기" }));
    await userEvent.selectOptions(form.getByLabelText("넣을 조합"), "1");
    expect(form.getAllByRole("button", { name: /^재료에서 빼기/ })).toHaveLength(3);
    await userEvent.click(form.getByRole("button", { name: /재료에서 빼기: 조합/ }));
    expect(form.getAllByRole("button", { name: /^재료에서 빼기/ })).toHaveLength(2);
    await userEvent.click(form.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(sent("POST /api/works/7/content/combos")).toHaveLength(1));
    expect(await sent("POST /api/works/7/content/combos")[0].req.json()).toEqual({
      이름: "완성", 재료: [{ 종류: "단서", 순서: 1 }, { 종류: "증언", 순서: 1 }],
    });
  });

  it("조합 편집에서 자기 자신은 재료로 고를 수 없다", async () => {
    bundle.combos = [{ 순서: 1, 이름: "안쪽", 재료: [] }, { 순서: 2, 이름: "바깥", 재료: [{ 종류: "조합", 순서: 1 }] }];
    renderApp("/works/7?tab=clues");
    const section = within(await screen.findByRole("region", { name: "조합" }));
    expect(section.getByText(/재료: 조합 1\. 안쪽/)).toBeInTheDocument();
    await userEvent.click(section.getAllByRole("button", { name: "편집" })[0]);
    const form = within(section.getByRole("form", { name: "조합 수정" }));
    await userEvent.click(form.getByRole("button", { name: "조합 넣기" }));
    expect(form.queryByRole("option", { name: /안쪽/ })).not.toBeInTheDocument();
    expect(form.getByRole("option", { name: /바깥/ })).toBeInTheDocument();
  });

  it("자료 탭의 공통 스토리를 부분으로 나누어 저장한다", async () => {
    Object.assign(work, { 공통스토리: "첫 글", 공통스토리_부분: [{ ID: "abc123", 본문: "첫 글" }] });
    routes["PATCH /api/works/7"] = () => json({ ...work, 공통스토리: "첫 글\n\n둘째 글", 공통스토리_부분: [{ ID: "abc123", 본문: "첫 글" }, { ID: "def456", 본문: "둘째 글" }] });
    renderApp("/works/7?tab=relations");
    const section = within(await screen.findByRole("region", { name: "공통 스토리" }));
    expect(section.getByLabelText(/공통 스토리 1/)).toHaveValue("첫 글");
    await userEvent.click(section.getByRole("button", { name: "부분 추가하기" }));
    await userEvent.type(section.getByLabelText(/공통 스토리 2/), "둘째 글");
    expect(section.getByText(/2개로 나누면|3개로 나누면/)).toBeInTheDocument();
    await userEvent.click(section.getByRole("button", { name: "공통 스토리 저장" }));
    await waitFor(() => expect(sent("PATCH /api/works/7")).toHaveLength(1));
    expect(await sent("PATCH /api/works/7")[0].req.json()).toEqual({ 공통스토리_부분: [{ ID: "abc123", 본문: "첫 글" }, { ID: null, 본문: "둘째 글" }] });
    expect(await section.findByRole("status")).toHaveTextContent("저장했습니다");
    expect(section.getByRole("button", { name: "공통 스토리 2 삭제" })).toBeInTheDocument();
    Object.assign(work, { 공통스토리: "", 공통스토리_부분: [] });
  });

  it("확인 탭은 게임 흐름을 세로로 보여 주고 확정 검사를 함께 한다", async () => {
    bundle.phases = [{ 순서: 1, 이름: "도입", 표시이름: "도입", 진행시간: 10 }, { 순서: 2, 이름: null, 표시이름: "조사", 진행시간: 20 }];
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
    expect(await sent("POST /api/works/7/content/clues")[0].req.json()).toEqual({ 이름: "편지", 공개이름: null, 인물_순서: 1 });
  });

  it("서버 오류는 그대로 보여 준다", async () => {
    routes["POST /api/works/7/content/endings"] = () => json({ detail: "내용: 비울 수 없는 항목입니다" }, 422);
    renderApp("/works/7?tab=endings");
    await userEvent.click(await screen.findByRole("button", { name: "엔딩 분기 추가" }));
    const form = screen.getByRole("form", { name: "엔딩 분기 추가" });
    await userEvent.click(within(form).getByRole("button", { name: "저장" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("내용: 비울 수 없는 항목입니다");
    expect(within(form).queryByLabelText("조건", { selector: "textarea" })).not.toBeInTheDocument();      // 식을 직접 쓰는 칸은 없다
  });

  describe("엔딩 조건 고르기", () => {
    const voteDef = {
      번호: 5, 이름: "최종 투표", 버전: 1, 설명: "d", 삭제됨: false, 사용설정: ["후보"],
      설정정의: [{ 키: "후보", 이름: "투표 후보", 종류: "후보" }],
      조건정의: [
        { 이름: "범인을 검거했다", 식: "결과_인물('최종 투표').범인", 인자: [] },
        { 이름: "이 인물이 가장 많은 표를 받았다", 식: "결과_인물('최종 투표').순서 == {인물}", 인자: [{ 키: "인물", 이름: "인물", 종류: "인물" }] },
        { 이름: "인물이 아닌 후보가 가장 많은 표를 받았다", 식: "결과_기타('최종 투표') == {후보}", 인자: [{ 키: "후보", 이름: "후보", 종류: "기타후보", 설정: "후보" }] },
      ],
    };
    const questionDef = {
      번호: 6, 이름: "개인 질문", 버전: 1, 설명: "d", 삭제됨: false, 사용설정: ["질문", "이름"],
      설정정의: [{ 키: "질문", 이름: "개인 질문", 종류: "질문" }, { 키: "이름", 이름: "이 카드의 이름", 종류: "글", 기본: "개인 질문" }],
      조건정의: [{
        이름: "이 인물이 이렇게 답했다", 식: "변수('{@이름}:{인물}') == {답}",
        인자: [{ 키: "인물", 이름: "인물", 종류: "질문인물", 설정: "질문" }, { 키: "답", 이름: "답", 종류: "질문답", 인물: "인물", 설정: "질문" }],
      }],
    };
    const setup = () => {
      bundle.characters = [
        { 순서: 1, 이름: "의사", 직업: null, NPC: false, 범인: true, 서사_부분수: 1 },
        { 순서: 2, 이름: "집사", 직업: null, NPC: false, 범인: false, 서사_부분수: 1 },
      ];
      bundle.phases = [{ 순서: 1, 이름: "투표", 표시이름: "투표", 진행시간: 10 }, { 순서: 2, 이름: "질문", 표시이름: "질문", 진행시간: 10 }];
      bundle["phase-steps"] = [
        { 번호: 9, 진행순서_순서: 1, 진행단계_번호: 5, 설정: { 후보: [1, 2, "사고사"] }, 표시이름: "최종 투표" },
        { 번호: 10, 진행순서_순서: 2, 진행단계_번호: 6, 설정: { 질문: { 2: { 질문: "알았습니까?", 선택: ["예", "아니오"] } } }, 표시이름: "개인 질문" },
      ];
      bundle.library = { phases: { 5: voteDef, 6: questionDef }, gimmicks: {} };
      routes["POST /api/works/7/content/endings"] = () => json({ 순서: 1 }, 201);
    };

    it("조건 항목을 고르고 빈칸을 채우면 식이 만들어져 저장된다", async () => {
      setup();
      renderApp("/works/7?tab=endings");
      await userEvent.click(await screen.findByRole("button", { name: "엔딩 분기 추가" }));
      const form = within(screen.getByRole("form", { name: "엔딩 분기 추가" }));
      await userEvent.type(form.getByLabelText("이름"), "검거");
      await userEvent.type(form.getByLabelText("내용"), "범인을 잡았다");
      expect(form.getByText("조건이 없으면 항상 나옵니다.")).toBeInTheDocument();
      await userEvent.click(form.getByRole("button", { name: "조건 더하기" }));
      await userEvent.selectOptions(form.getByLabelText("조건 1"), "범인을 검거했다");
      await userEvent.click(form.getByRole("button", { name: "조건 더하기" }));
      await userEvent.selectOptions(form.getByLabelText("조건 2 카드"), "10");
      await userEvent.selectOptions(form.getByLabelText("조건 2"), "이 인물이 이렇게 답했다");
      await userEvent.selectOptions(form.getByLabelText("조건 2 인물"), "2");
      await userEvent.selectOptions(form.getByLabelText("조건 2 답"), "예");
      await userEvent.click(form.getByRole("button", { name: "저장" }));
      await waitFor(() => expect(sent("POST /api/works/7/content/endings")).toHaveLength(1));
      const body = await sent("POST /api/works/7/content/endings")[0].req.json();
      expect(body.조건.식).toBe("(결과_인물('최종 투표').범인) and (변수('개인 질문:2') == \"예\")");
      expect(body.조건.구성).toEqual([
        { 카드: 9, 조건: "범인을 검거했다", 인자: {} },
        { 카드: 10, 조건: "이 인물이 이렇게 답했다", 인자: { 인물: 2, 답: "예" } },
      ]);
    });

    it("빈칸이 남았으면 저장하지 않고, 인물이 아닌 후보는 카드 설정에서 가져온다", async () => {
      setup();
      renderApp("/works/7?tab=endings");
      await userEvent.click(await screen.findByRole("button", { name: "엔딩 분기 추가" }));
      const form = within(screen.getByRole("form", { name: "엔딩 분기 추가" }));
      await userEvent.type(form.getByLabelText("이름"), "사고사");
      await userEvent.type(form.getByLabelText("내용"), "사고였다");
      await userEvent.click(form.getByRole("button", { name: "조건 더하기" }));
      await userEvent.selectOptions(form.getByLabelText("조건 1"), "인물이 아닌 후보가 가장 많은 표를 받았다");
      expect(form.getByRole("option", { name: "사고사" })).toBeInTheDocument();
      await userEvent.click(form.getByRole("button", { name: "저장" }));
      expect(await form.findByRole("alert")).toHaveTextContent("조건 고르기를 끝내 주세요");
      expect(sent("POST /api/works/7/content/endings")).toHaveLength(0);
      await userEvent.selectOptions(form.getByLabelText("조건 1 후보"), "사고사");
      await userEvent.click(form.getByRole("button", { name: "저장" }));
      await waitFor(() => expect(sent("POST /api/works/7/content/endings")).toHaveLength(1));
      expect((await sent("POST /api/works/7/content/endings")[0].req.json()).조건.식).toBe("(결과_기타('최종 투표') == \"사고사\")");
    });

    it("식으로 저장된 옛 조건은 코드로 쓴 조건이라고만 보이고, 지우면 고르는 방식이 된다", async () => {
      setup();
      bundle.endings = [{ 순서: 1, 이름: "옛 엔딩", 내용: "x", 조건: { 식: "변수('a') == 1" } }];
      renderApp("/works/7?tab=endings");
      await userEvent.click(await screen.findByRole("button", { name: "편집" }));
      const form = within(screen.getByRole("form", { name: "엔딩 분기 수정" }));
      expect(form.getByText("변수('a') == 1")).toBeInTheDocument();
      await userEvent.click(form.getByRole("button", { name: /고르는 방식으로 바꾸기/ }));
      expect(form.getByText("조건이 없으면 항상 나옵니다.")).toBeInTheDocument();
    });
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
          const width = sib.matches("[data-slot]")
            ? (sib.classList.contains("open") ? (sib.classList.contains("wide") ? W : 56) : 0)       // 접힌 빈자리는 폭 0
            : sib.matches("[data-tile]") ? (sib.classList.contains("collapsed") ? 0 : W) : 0;
          if (sib === this) return rect(left, 100, width, 150);
          left += width > 0 ? width + GAP : 0;
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
    bundle.phases = [{ 순서: 1, 이름: "도입", 표시이름: "도입", 진행시간: 10 }, { 순서: 2, 이름: null, 표시이름: "2차 조사", 진행시간: 20 }];
    (bundle.library as { phases: object }).phases = { 5: { 번호: 5, 이름: "조사", 버전: 2, 설명: "d", 삭제됨: false } };
    bundle["phase-steps"] = [
      { 번호: 9, 진행순서_순서: 1, 진행단계_번호: 5, 설정: null, 표시이름: "1차 조사" },
      { 번호: 10, 진행순서_순서: 2, 진행단계_번호: 5, 설정: { 내용유지: false, 횟수: 3 }, 표시이름: "2차 조사" },
    ];
  };
  const editor = () => within(screen.getByRole("region", { name: "페이즈 편집" }));
  const pickCard = (name: string) => userEvent.click(editor().getByRole("button", { name }));
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

    it("빈 흐름에 진행카드를 끌어다 놓으면 첫 페이즈가 만들어지고 거기에 붙는다", async () => {
      withTray([5]);
      routes["POST /api/works/7/phases/insert"] = () => json({ phases: [{ 순서: 1, 이름: null, 진행시간: 30 }] }, 201);
      routes["POST /api/works/7/content/phase-steps"] = () => json({ 번호: 11 }, 201);
      renderApp("/works/7?tab=phases");
      const card = await screen.findByLabelText("진행단계 카드 조사");
      drag(card, [[100, 150]], false);
      expect(document.querySelectorAll(".flow-slot.open")).toHaveLength(1);        // 올려 둔 자리에 빈자리가 열린다
      fireEvent.pointerUp(window, { clientX: 100, clientY: 150 });
      await waitFor(() => expect(sent("POST /api/works/7/content/phase-steps")).toHaveLength(1));
      expect(await sent("POST /api/works/7/phases/insert")[0].req.json()).toEqual({ position: 1, 이름: null, 진행시간: 30 });
      expect(await sent("POST /api/works/7/content/phase-steps")[0].req.json()).toEqual({ 진행순서_순서: 1, 진행단계_번호: 5 });
      expect(document.querySelector(".drag-ghost")).toBeNull();                    // 놓으면 끌던 복제본이 사라진다
    });

    it("새 페이즈 카드는 없다(페이즈는 진행카드를 놓아서 만든다)", async () => {
      renderApp("/works/7?tab=phases");
      await screen.findByRole("region", { name: "진행카드" });
      expect(screen.queryByLabelText("새 페이즈 카드")).not.toBeInTheDocument();
    });

    it("흐름 밖에서 놓으면 아무것도 하지 않는다", async () => {
      renderApp("/works/7?tab=phases");
      withTray([5]);
      drag(await screen.findByLabelText("진행단계 카드 조사"), [[100, 600]]);
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
      expect(screen.getByLabelText("진행단계 카드 조사")).toHaveTextContent("조사");
      expect(screen.getByLabelText("진행단계 카드 조사")).not.toHaveTextContent(/진행단계 · v/);
      expect(JSON.parse(localStorage.getItem("mm.tray.7")!)).toEqual({ steps: [5], gimmicks: [] });
      await userEvent.click(screen.getByRole("button", { name: "조사 v2 빼기" }));                 // 카드의 ×
      expect(screen.queryByLabelText("진행단계 카드 조사")).not.toBeInTheDocument();
    });

    it("전체 선택은 이름마다 가장 높은 버전만 고르고, 검색 중이면 보이는 것만, 다시 누르면 해제한다", async () => {
      routes["GET /api/library/phases"] = () => json([
        { 번호: 5, 이름: "조사", 버전: 2, 설명: null, 변경내역: null, 공통: false },
        { 번호: 4, 이름: "조사", 버전: 1, 설명: null, 변경내역: null, 공통: false },
        { 번호: 6, 이름: "토론", 버전: 1, 설명: null, 변경내역: null, 공통: false },
        { 번호: 7, 이름: "밀담", 버전: 1, 설명: null, 변경내역: null, 공통: false },
      ]);
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("button", { name: "진행카드 불러오기" }));
      const dialog = within(screen.getByRole("dialog", { name: "진행카드 불러오기" }));
      await userEvent.type(dialog.getByLabelText("이름 검색"), "토");
      await userEvent.click(dialog.getByRole("button", { name: "전체 선택" }));
      expect(dialog.getByRole("button", { name: "토론 v1" })).toHaveAttribute("aria-pressed", "true");
      expect(dialog.getByRole("button", { name: "전체 해제" })).toBeInTheDocument();
      await userEvent.clear(dialog.getByLabelText("이름 검색"));
      expect(dialog.getByRole("button", { name: "밀담 v1" })).toHaveAttribute("aria-pressed", "false");   // 검색에서 빠진 것은 그대로
      await userEvent.click(dialog.getByRole("button", { name: "전체 선택" }));
      expect(JSON.parse(localStorage.getItem("mm.tray.7")!).steps.sort()).toEqual([5, 6, 7]);                // 조사는 v2(5)만, 옛 버전(4)은 빠진다
      await userEvent.click(dialog.getByRole("button", { name: "전체 해제" }));
      expect(JSON.parse(localStorage.getItem("mm.tray.7")!).steps).toEqual([]);
      await userEvent.click(dialog.getByRole("tab", { name: "기믹" }));
      expect(dialog.getByRole("button", { name: /전체/ })).toBeDisabled();                                  // 기믹이 없으면 누를 수 없다
      expect(dialog.queryByRole("button", { name: "닫기" })).not.toBeInTheDocument();                        // 위쪽 닫기는 없고
      await userEvent.click(dialog.getByRole("button", { name: "확인" }));                                    // 아래 가운데의 확인으로 닫는다
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
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
      expect(second.querySelector(".tile-name")).toHaveTextContent("2차 조사");          // 이름을 정하지 않았으면 붙은 진행단계 이름을 따라간다
      expect(within(second).getByLabelText("세부 설정 있음")).toBeInTheDocument();
      expect(first.querySelector(".grip")).toBeNull();                          // 점 여섯 개 손잡이는 없다
      expect(screen.queryByRole("button", { name: /편집$/ })).not.toBeInTheDocument();
    });

    it("이름을 정하지 않은 페이즈는 붙은 진행단계 이름을 이어 보여 주고(조사·밀담), 비어 있으면 '이름 없음'이다", async () => {
      bundle.phases = [{ 순서: 1, 이름: null, 표시이름: "조사·밀담", 진행시간: 30 }, { 순서: 2, 이름: null, 표시이름: null, 진행시간: 30 }];
      bundle["phase-steps"] = [
        { 번호: 9, 진행순서_순서: 1, 진행단계_번호: 5, 설정: null, 표시이름: "조사" },
        { 번호: 10, 진행순서_순서: 1, 진행단계_번호: 6, 설정: null, 표시이름: "밀담" },
      ];
      (bundle.library as { phases: object }).phases = {
        5: { 번호: 5, 이름: "조사", 버전: 1, 설명: "", 삭제됨: false }, 6: { 번호: 6, 이름: "밀담", 버전: 1, 설명: "", 삭제됨: false },
      };
      renderApp("/works/7?tab=phases");
      await screen.findByRole("listitem", { name: "페이즈 1" });
      expect(tile(1).querySelector(".tile-name")).toHaveTextContent("조사·밀담");
      expect(tile(2).querySelector(".tile-name")).toHaveTextContent("이름 없음");
      await userEvent.click(tile(1));
      expect(editor().getByLabelText("페이즈 이름")).toHaveValue("");                                // 정한 이름은 비어 있고
      expect(editor().getByLabelText("페이즈 이름")).toHaveAttribute("placeholder", "조사·밀담");     // 따라가는 이름이 보인다
      expect(editor().queryByText(/비워 두면/)).not.toBeInTheDocument();                                 // 설명 글은 없다
    });

    it("처음에는 수정 패널이 닫혀 있고, 카드를 한 번 누르면 그 페이즈가 열린다", async () => {
      renderApp("/works/7?tab=phases");
      await screen.findByRole("listitem", { name: "페이즈 1" });
      expect(screen.queryByRole("region", { name: "페이즈 편집" })).not.toBeInTheDocument();
      await userEvent.click(tile(2));
      expect(screen.getByRole("heading", { name: "02" })).toBeInTheDocument();
      expect(editor().queryByRole("group", { name: "2차 조사 수정" })).not.toBeInTheDocument();   // 카드를 고르기 전에는 수정 항목이 없다
      await pickCard("2차 조사");
      expect(editor().getByRole("group", { name: "2차 조사 수정" })).toHaveTextContent("v2");
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
      expect(document.querySelector(".flow-slot.open")).toBeNull();
    });

    it("진행카드를 페이즈 가장자리(틈)에 올리면 그 자리만 열리고, 놓으면 새 페이즈로 끼워 넣어 거기에 붙인다", async () => {
      routes["POST /api/works/7/phases/insert"] = () => json({ phases: [
        { 순서: 1, 이름: "도입", 진행시간: 10 }, { 순서: 3, 이름: null, 진행시간: 30 }, { 순서: 2, 이름: null, 진행시간: 20 },
      ] }, 201);
      routes["POST /api/works/7/content/phase-steps"] = () => json({ 번호: 11 }, 201);
      renderApp("/works/7?tab=phases");
      const card = await screen.findByLabelText("진행단계 카드 조사");
      drag(card, [[tileX(1) + 4, 150]], false);                                   // 2번째 카드의 왼쪽 가장자리
      const open = document.querySelectorAll(".flow-slot.open");
      expect(open).toHaveLength(1);                                               // 빈자리는 올려 둔 한 곳만 열린다
      expect(open[0].previousElementSibling).toBe(tile(1));                       // 1번과 2번 사이
      expect(open[0].nextElementSibling).toBe(tile(2));
      expect(open[0]).not.toHaveClass("wide");                                    // 진행카드를 끌 때는 좁은 빈자리
      expect(open[0]).toHaveTextContent("");                                      // 표시(+)는 없다 — 붙일 페이즈를 강조할 때만 표시한다
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
      expect(await screen.findByRole("heading", { name: "02" })).toBeInTheDocument();
      expect(calls.filter((c) => c.key.startsWith("PATCH"))).toHaveLength(0);
    });

    it("페이즈 카드를 끌면 카드 자체가 빠져나가 따라오고, 올려 둔 자리에 폭이 같은 빈자리가 열려 순서가 바뀐다", async () => {
      routes["POST /api/works/7/phases/1/move"] = () => json({ phases: [] });
      renderApp("/works/7?tab=phases");
      const first = await screen.findByRole("listitem", { name: "페이즈 1" });
      drag(first, [[10, 150], [tileX(1) + 150, 150]], false);                    // 두 번째 카드의 오른쪽 절반 → 그 뒤
      expect(screen.queryByRole("listitem", { name: "페이즈 1" })).not.toBeInTheDocument();       // 끌고 있는 카드는 흐름에서 읽히지 않는다
      const origin = document.querySelector("li.drag-origin")!;
      expect(origin).toHaveClass("collapsed");                                                    // 제자리는 접히고
      const open = document.querySelector(".flow-slot.open")!;
      expect(open).toHaveClass("wide");                                                           // 올려 둔 자리에 카드 폭의 빈자리가 열린다
      expect(open.previousElementSibling).toBe(tile(2));                                          // 2번째 카드의 뒤
      expect(document.querySelector(".drag-ghost")).not.toBeNull();
      fireEvent.pointerUp(window, { clientX: tileX(1) + 150, clientY: 150 });
      await waitFor(() => expect(sent("POST /api/works/7/phases/1/move")).toHaveLength(1));
      expect(await sent("POST /api/works/7/phases/1/move")[0].req.json()).toEqual({ position: 2 });
    });

    it("페이즈 카드를 놓으면 서버가 응답하기 전에도 놓은 자리에 그대로 있고, 원래 자리로 돌아갔다 가지 않는다", async () => {
      twoPhases();
      let release!: () => void;
      const gate = new Promise<void>((r) => (release = r));
      routes["POST /api/works/7/phases/1/move"] = async () => {
        await gate;
        return json({ phases: [] });
      };
      renderApp("/works/7?tab=phases");
      const first = await screen.findByRole("listitem", { name: "페이즈 1" });
      expect(tile(1).querySelector(".tile-name")).toHaveTextContent("도입");
      drag(first, [[10, 150], [tileX(1) + 150, 150]]);                           // 두 번째 카드 뒤에 놓는다
      expect(sent("POST /api/works/7/phases/1/move")).toHaveLength(1);
      expect(tile(1).querySelector(".tile-name")).toHaveTextContent("2차 조사");   // 응답 전에 벌써 새 자리
      expect(tile(2).querySelector(".tile-name")).toHaveTextContent("도입");
      expect(document.querySelector("ol.flow")).toHaveClass("settling");           // 놓은 직후에는 움직임(전환) 없이
      expect(document.querySelector(".flow-slot.open")).toBeNull();
      release();
      await waitFor(() => expect(document.querySelector("ol.flow")).not.toHaveClass("settling"));
    });

    it("페이즈 카드를 제자리에 놓으면 서버에 요청하지 않는다", async () => {
      renderApp("/works/7?tab=phases");
      drag(await screen.findByRole("listitem", { name: "페이즈 1" }), [[10, 150]]);
      await new Promise((r) => setTimeout(r, 30));
      expect(calls.filter((c) => c.key.includes("/move"))).toHaveLength(0);
      expect(screen.getByRole("listitem", { name: "페이즈 1" })).toBeInTheDocument();         // 카드가 돌아온다
    });

    it("수정 패널의 화살표는 페이즈를 옮기지 않고 수정하는 페이즈를 이전/다음으로 바꾼다", async () => {
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 1" }));
      expect(screen.getByRole("heading", { name: "01" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "이전 페이즈 수정" })).toBeDisabled();              // 맨 앞에서는 이전이 없다
      expect(screen.getByRole("button", { name: "이전 페이즈 수정" })).toHaveTextContent("←");
      expect(screen.getByRole("button", { name: "다음 페이즈 수정" })).toHaveTextContent("→");      // 글자 없이 화살표만
      await userEvent.click(screen.getByRole("button", { name: "다음 페이즈 수정" }));
      expect(screen.getByRole("heading", { name: "02" })).toBeInTheDocument();
      expect(editor().getByRole("button", { name: "2차 조사" })).toBeInTheDocument();                 // 2번째 페이즈의 카드 목록으로 바뀐다
      expect(screen.getByRole("button", { name: "다음 페이즈 수정" })).toBeDisabled();              // 맨 뒤에서는 다음이 없다
      await userEvent.click(screen.getByRole("button", { name: "이전 페이즈 수정" }));
      expect(screen.getByRole("heading", { name: "01" })).toBeInTheDocument();
      expect(screen.getByRole("listitem", { name: "페이즈 1" })).toHaveClass("selected");            // 강조도 따라간다
      expect(calls.filter((c) => c.key.includes("/move"))).toHaveLength(0);                          // 서버에는 아무것도 보내지 않는다
    });

    it("수정 패널에는 진행단계·기믹 고르기와 붙이기 칸이 없다", async () => {
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 1" }));
      expect(editor().queryByRole("combobox")).not.toBeInTheDocument();
      expect(editor().queryByRole("button", { name: "붙이기" })).not.toBeInTheDocument();
    });

    it("수정 패널에서 이름·시간을 저장하고, 서버 값이 바뀌면 입력칸도 따라 바뀐다", async () => {
      routes["PATCH /api/works/7/content/phases/2"] = () => {
        bundle.phases = [{ 순서: 1, 이름: "도입", 표시이름: "도입", 진행시간: 10 }, { 순서: 2, 이름: "토론", 표시이름: "토론", 진행시간: 45 }];
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

    it("페이즈 삭제는 확인창 없이 바로 서버에 요청하고 수정 패널을 닫는다", async () => {
      routes["DELETE /api/works/7/phases/2"] = () => json({ phases: [] });
      const confirm = vi.spyOn(window, "confirm");
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 2" }));
      await userEvent.click(screen.getByRole("button", { name: "페이즈 2 삭제" }));
      await waitFor(() => expect(sent("DELETE /api/works/7/phases/2")).toHaveLength(1));
      expect(confirm).not.toHaveBeenCalled();
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

    it("붙은 진행단계는 목록으로 보이고, 하나를 고르면 수정 항목이 나타나며, 탭을 남기지 않기를 고르면 설정에 담고, 기본값이면 비운다", async () => {
      routes["PATCH /api/works/7/content/phase-steps/9"] = () => json({});
      routes["PATCH /api/works/7/content/phase-steps/10"] = () => json({});
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 1" }));
      await pickCard("1차 조사");
      const first = within(editor().getByRole("group", { name: "1차 조사 수정" }));
      expect(first.getByLabelText(/내용 유지/)).toBeChecked();
      await userEvent.click(first.getByLabelText(/내용 유지/));
      await userEvent.click(first.getByRole("button", { name: "설정 저장" }));
      expect(await sent("PATCH /api/works/7/content/phase-steps/9")[0].req.json()).toEqual({ 설정: { 내용유지: false } });

      await userEvent.click(tile(2));
      await pickCard("2차 조사");
      const second = within(editor().getByRole("group", { name: "2차 조사 수정" }));
      expect(second.getByLabelText(/내용 유지/)).not.toBeChecked();
      expect(second.getByLabelText(/JSON/)).toHaveValue(JSON.stringify({ 횟수: 3 }, null, 2));
      await userEvent.click(second.getByLabelText(/내용 유지/));
      await userEvent.clear(second.getByLabelText(/JSON/));
      await userEvent.click(second.getByRole("button", { name: "설정 저장" }));
      expect(await sent("PATCH /api/works/7/content/phase-steps/10")[0].req.json()).toEqual({ 설정: null });
    });

    it("스크립트가 개인 서사 공개를 쓰는 카드는 인물마다 보여 줄 서사를 고르고, 기본(서사 1)이면 저장하지 않는다", async () => {
      routes["PATCH /api/works/7/content/phase-steps/9"] = () => json({});
      twoPhases();
      (bundle.library as { phases: Record<string, object> }).phases[5] = { 번호: 5, 이름: "프로필 숙지", 버전: 1, 설명: "d", 삭제됨: false, 사용설정: ["개인서사공개"] };
      bundle.characters = [
        { 순서: 1, 이름: "의사", 직업: null, NPC: false, 범인: false, 서사_부분수: 2 },
        { 순서: 2, 이름: "집사", 직업: null, NPC: false, 범인: false, 서사_부분수: 1 },
        { 순서: 3, 이름: "피해자", 직업: null, NPC: true, 범인: false, 서사_부분수: 1 },
      ];
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 1" }));
      await pickCard("1차 조사");
      const card = within(editor().getByRole("group", { name: "1차 조사 수정" }));
      expect(card.queryByRole("group", { name: "피해자의 개인 서사 공개" })).not.toBeInTheDocument();   // NPC 는 고르지 않는다
      const doctor = within(card.getByRole("group", { name: "의사의 개인 서사 공개" }));
      expect(doctor.getByLabelText("서사 1")).toBeChecked();
      expect(doctor.getByLabelText("서사 2")).not.toBeChecked();
      await userEvent.click(doctor.getByLabelText("서사 2"));
      await userEvent.click(card.getByRole("button", { name: "설정 저장" }));
      expect(await sent("PATCH /api/works/7/content/phase-steps/9")[0].req.json()).toEqual({ 설정: { 개인서사공개: { 1: [1, 2] } } });
    });

    it("개인 서사 공개를 쓰지 않는 카드에는 서사 선택이 없고, 없는 서사를 고른 설정은 경고한다", async () => {
      twoPhases();
      (bundle.library as { phases: Record<string, object> }).phases[5] = { 번호: 5, 이름: "프로필 숙지", 버전: 1, 설명: "d", 삭제됨: false, 사용설정: ["개인서사공개"] };
      bundle.characters = [{ 순서: 1, 이름: "의사", 직업: null, NPC: false, 범인: false, 서사_부분수: 1 }];
      (bundle["phase-steps"] as { 설정: unknown }[])[0].설정 = { 개인서사공개: { 1: [1, 3] } };
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 1" }));
      await pickCard("1차 조사");
      const doctor = within(editor().getByRole("group", { name: "의사의 개인 서사 공개" }));
      expect(doctor.getByRole("status")).toHaveTextContent("서사 3은(는) 없습니다(서사 1개)");
    });

    it("스크립트가 후보를 쓰는 카드는 투표 후보를 고르고, 기본(플레이어 인물 모두)이면 저장하지 않는다", async () => {
      routes["PATCH /api/works/7/content/phase-steps/9"] = () => json({});
      twoPhases();
      (bundle.library as { phases: Record<string, object> }).phases[5] = { 번호: 5, 이름: "최종 투표", 버전: 1, 설명: "d", 삭제됨: false, 사용설정: ["후보"] };
      bundle.characters = [
        { 순서: 1, 이름: "의사", 직업: null, NPC: false, 범인: false, 서사_부분수: 1 },
        { 순서: 2, 이름: "집사", 직업: null, NPC: false, 범인: false, 서사_부분수: 1 },
        { 순서: 3, 이름: "피해자", 직업: null, NPC: true, 범인: false, 서사_부분수: 1 },
      ];
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 1" }));
      await pickCard("1차 조사");
      const card = within(editor().getByRole("group", { name: "1차 조사 수정" }));
      expect(card.getByLabelText("의사")).toBeChecked();
      expect(card.getByLabelText("집사")).toBeChecked();
      expect(card.getByLabelText("피해자 (NPC)")).not.toBeChecked();
      await userEvent.click(card.getByRole("button", { name: "설정 저장" }));
      expect(await sent("PATCH /api/works/7/content/phase-steps/9")[0].req.json()).toEqual({ 설정: null });        // 기본과 같으면 저장하지 않는다
      await userEvent.click(card.getByLabelText("피해자 (NPC)"));
      await userEvent.click(card.getByLabelText("집사"));
      await userEvent.click(card.getByRole("button", { name: "설정 저장" }));
      await waitFor(() => expect(sent("PATCH /api/works/7/content/phase-steps/9")).toHaveLength(2));
      expect(await sent("PATCH /api/works/7/content/phase-steps/9")[1].req.json()).toEqual({ 설정: { 후보: [1, 3] } });
    });

    it("개인 질문 카드는 인물마다 질문과 선택지를 적고, 비운 인물은 저장하지 않는다", async () => {
      routes["PATCH /api/works/7/content/phase-steps/9"] = () => json({});
      twoPhases();
      (bundle.library as { phases: Record<string, object> }).phases[5] = { 번호: 5, 이름: "개인 질문", 버전: 1, 설명: "d", 삭제됨: false, 사용설정: ["질문"] };
      bundle.characters = [
        { 순서: 1, 이름: "의사", 직업: null, NPC: false, 범인: false, 서사_부분수: 1 },
        { 순서: 2, 이름: "집사", 직업: null, NPC: false, 범인: false, 서사_부분수: 1 },
        { 순서: 3, 이름: "피해자", 직업: null, NPC: true, 범인: false, 서사_부분수: 1 },
      ];
      (bundle["phase-steps"] as { 설정: unknown }[])[0].설정 = { 질문: { 2: "기존 질문" } };
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 1" }));
      await pickCard("1차 조사");
      const card = within(editor().getByRole("group", { name: "1차 조사 수정" }));
      expect(card.queryByRole("group", { name: "피해자의 질문" })).not.toBeInTheDocument();          // NPC 는 답하지 않는다
      expect(card.getByLabelText("집사 질문")).toHaveValue("기존 질문");
      await userEvent.type(card.getByLabelText("의사 질문"), "비밀을 알았습니까?");
      await userEvent.type(card.getByLabelText("의사 새 선택지"), "예, 하지만 늦게{Enter}");              // 쉼표가 들어가도 하나의 선택지이다
      await userEvent.type(card.getByLabelText("의사 새 선택지"), "아니오");
      await userEvent.click(card.getByRole("button", { name: "의사 선택지 추가" }));
      await userEvent.type(card.getByLabelText("의사 새 선택지"), "삭제할 것{Enter}");
      await userEvent.click(card.getByRole("button", { name: "의사 선택지 삭제할 것 삭제" }));
      expect(card.getByText("선택지 없음(글로 답함)")).toBeInTheDocument();                              // 집사는 선택지가 없다
      await userEvent.click(card.getByRole("button", { name: "설정 저장" }));
      expect(await sent("PATCH /api/works/7/content/phase-steps/9")[0].req.json()).toEqual({
        설정: { 질문: { 1: { 질문: "비밀을 알았습니까?", 선택: ["예, 하지만 늦게", "아니오"] }, 2: "기존 질문" } },
      });
    });

    it("투표 후보에 사고사·자살 같은 인물이 아닌 후보를 더하고 뺄 수 있다", async () => {
      routes["PATCH /api/works/7/content/phase-steps/9"] = () => json({});
      twoPhases();
      (bundle.library as { phases: Record<string, object> }).phases[5] = { 번호: 5, 이름: "최종 투표", 버전: 1, 설명: "d", 삭제됨: false, 사용설정: ["후보"] };
      bundle.characters = [
        { 순서: 1, 이름: "의사", 직업: null, NPC: false, 범인: false, 서사_부분수: 1 },
        { 순서: 2, 이름: "집사", 직업: null, NPC: false, 범인: false, 서사_부분수: 1 },
      ];
      (bundle["phase-steps"] as { 설정: unknown }[])[0].설정 = { 후보: [1, 2, "자살"] };
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 1" }));
      await pickCard("1차 조사");
      const card = within(editor().getByRole("group", { name: "1차 조사 수정" }));
      expect(card.getByText("자살")).toBeInTheDocument();
      await userEvent.type(card.getByLabelText("인물이 아닌 후보"), "사고사{Enter}");
      await userEvent.click(card.getByRole("button", { name: "자살 후보 삭제" }));
      await userEvent.click(card.getByRole("button", { name: "설정 저장" }));
      expect(await sent("PATCH /api/works/7/content/phase-steps/9")[0].req.json()).toEqual({ 설정: { 후보: [1, 2, "사고사"] } });
    });

    it("투표 동률·능력 대상 같은 단순 설정은 선택지와 입력칸으로 정하고, 기본값과 같으면 저장하지 않는다", async () => {
      routes["PATCH /api/works/7/content/phase-steps/9"] = () => json({});
      twoPhases();
      (bundle.library as { phases: Record<string, object> }).phases[5] = {
        번호: 5, 이름: "최종 투표", 버전: 1, 설명: "d", 삭제됨: false, 사용설정: ["동률", "재투표한도", "대상", "횟수"],
        설정정의: [
          { 키: "동률", 이름: "투표가 동률일 때", 종류: "선택", 기본: "구속없음", 선택: [["구속없음", "결과 없음"], ["재투표", "재투표"]] },
          { 키: "재투표한도", 이름: "재투표 한도(0은 한도 없음)", 종류: "숫자", 기본: 1, 최소: 0 },
          { 키: "대상", 이름: "능력의 지목 대상", 종류: "여러선택", 기본: ["인물"], 선택: [["인물", "인물"], ["장소", "장소"], ["단서", "단서"]] },
          { 키: "횟수", 이름: "조사 횟수(1인당)", 종류: "숫자", 기본: 3, 최소: 1 },
        ],
      };
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 1" }));
      await pickCard("1차 조사");
      const card = within(editor().getByRole("group", { name: "1차 조사 수정" }));
      expect(card.queryByLabelText("재투표 후보")).not.toBeInTheDocument();                         // 스크립트가 쓰지 않는 설정은 보이지 않는다
      expect(card.queryByLabelText(/그 밖의 세부 설정/)).not.toBeInTheDocument();                   // 스크립트가 칸을 정한 카드에는 JSON 칸이 없다
      await userEvent.click(card.getByRole("button", { name: "설정 저장" }));
      expect(await sent("PATCH /api/works/7/content/phase-steps/9")[0].req.json()).toEqual({ 설정: null });
      await userEvent.selectOptions(card.getByLabelText("투표가 동률일 때"), "재투표");
      await userEvent.clear(card.getByLabelText("재투표 한도(0은 한도 없음)"));
      await userEvent.type(card.getByLabelText("재투표 한도(0은 한도 없음)"), "0");
      await userEvent.clear(card.getByLabelText("조사 횟수(1인당)"));
      await userEvent.type(card.getByLabelText("조사 횟수(1인당)"), "5");
      await userEvent.click(card.getByLabelText("장소"));
      await userEvent.click(card.getByLabelText("단서"));
      await userEvent.click(card.getByRole("button", { name: "설정 저장" }));
      await waitFor(() => expect(sent("PATCH /api/works/7/content/phase-steps/9")).toHaveLength(2));
      expect(await sent("PATCH /api/works/7/content/phase-steps/9")[1].req.json()).toEqual({
        설정: { 동률: "재투표", 재투표한도: 0, 횟수: 5, 대상: ["인물", "장소", "단서"] },
      });
      await userEvent.click(card.getByLabelText("인물"));                                           // 하나도 고르지 않으면 저장하지 않는다
      await userEvent.click(card.getByLabelText("장소"));
      await userEvent.click(card.getByLabelText("단서"));
      await userEvent.click(card.getByRole("button", { name: "설정 저장" }));
      expect(await card.findByText(/능력의 지목 대상: 하나 이상 골라 주세요/)).toBeInTheDocument();
      expect(sent("PATCH /api/works/7/content/phase-steps/9")).toHaveLength(2);
    });

    it("공통 스토리 카드는 보여 줄 부분 번호를 고르고(기본 1부분), 탭 이름·방식도 입력칸으로 정한다", async () => {
      routes["PATCH /api/works/7/content/phase-steps/9"] = () => json({});
      twoPhases();
      bundle.story = { 공통스토리_부분수: 3 };
      (bundle.library as { phases: Record<string, object> }).phases[5] = {
        번호: 5, 이름: "공통 스토리", 버전: 1, 설명: "d", 삭제됨: false, 사용설정: ["공개부분", "탭이름", "탭방식"],
        설정정의: [
          { 키: "공개부분", 이름: "보여 줄 공통 스토리 부분", 종류: "공통서사" },
          { 키: "탭이름", 이름: "탭 이름", 종류: "글", 기본: "" },
          { 키: "탭방식", 이름: "탭에 보여 주는 방식", 종류: "선택", 기본: "새탭", 선택: [["새탭", "새 탭을 추가"], ["이어서", "기존 탭에 이어서 보여 주기"]] },
        ],
      };
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 1" }));
      await pickCard("1차 조사");
      const card = within(editor().getByRole("group", { name: "1차 조사 수정" }));
      expect(card.getByLabelText("1부분")).toBeChecked();
      expect(card.getByLabelText("2부분")).not.toBeChecked();
      expect(card.getByLabelText("3부분")).not.toBeChecked();
      await userEvent.click(card.getByRole("button", { name: "설정 저장" }));
      expect(await sent("PATCH /api/works/7/content/phase-steps/9")[0].req.json()).toEqual({ 설정: null });         // 기본과 같으면 저장하지 않는다
      await userEvent.click(card.getByLabelText("1부분"));
      await userEvent.click(card.getByLabelText("3부분"));
      await userEvent.type(card.getByLabelText("탭 이름"), "사건의 배경");
      await userEvent.selectOptions(card.getByLabelText("탭에 보여 주는 방식"), "이어서");
      await userEvent.click(card.getByRole("button", { name: "설정 저장" }));
      await waitFor(() => expect(sent("PATCH /api/works/7/content/phase-steps/9")).toHaveLength(2));
      expect(await sent("PATCH /api/works/7/content/phase-steps/9")[1].req.json()).toEqual({
        설정: { 공개부분: [3], 탭이름: "사건의 배경", 탭방식: "이어서" },
      });
      await userEvent.click(card.getByLabelText("3부분"));                                              // 하나도 고르지 않으면 저장하지 않는다
      await userEvent.click(card.getByRole("button", { name: "설정 저장" }));
      expect(await card.findByText(/하나 이상 골라 주세요/)).toBeInTheDocument();
    });

    it("칸을 선언하지 않은 진행단계(옛 방식)에는 JSON 칸이 남아 있다", async () => {
      twoPhases();
      (bundle["phase-steps"] as { 설정: unknown }[])[0].설정 = { 알수없는설정: 3 };
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 1" }));
      await pickCard("1차 조사");
      const card = within(editor().getByRole("group", { name: "1차 조사 수정" }));
      expect(card.getByLabelText(/그 밖의 세부 설정/)).toHaveValue(JSON.stringify({ 알수없는설정: 3 }, null, 2));
    });

    it("칸을 선언한 진행단계는 JSON 칸 없이 저장하고, 칸에 없는 기존 값은 그대로 둔다", async () => {
      routes["PATCH /api/works/7/content/phase-steps/9"] = () => json({});
      twoPhases();
      (bundle.library as { phases: Record<string, object> }).phases[5] = {
        번호: 5, 이름: "조사", 버전: 1, 설명: "d", 삭제됨: false, 사용설정: ["횟수"],
        설정정의: [{ 키: "횟수", 이름: "조사 횟수(1인당)", 종류: "숫자", 기본: 3, 최소: 1 }],
      };
      (bundle["phase-steps"] as { 설정: unknown }[])[0].설정 = { 알수없는설정: 3 };
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 1" }));
      await pickCard("1차 조사");
      const card = within(editor().getByRole("group", { name: "1차 조사 수정" }));
      expect(card.queryByLabelText(/그 밖의 세부 설정/)).not.toBeInTheDocument();
      await userEvent.clear(card.getByLabelText("조사 횟수(1인당)"));
      await userEvent.type(card.getByLabelText("조사 횟수(1인당)"), "5");
      await userEvent.click(card.getByRole("button", { name: "설정 저장" }));
      expect(await sent("PATCH /api/works/7/content/phase-steps/9")[0].req.json()).toEqual({ 설정: { 알수없는설정: 3, 횟수: 5 } });
    });

    it("스크립트가 개인 서사 공개를 쓰지 않는 카드에는 서사 선택이 없다", async () => {
      twoPhases();
      bundle.characters = [{ 순서: 1, 이름: "의사", 직업: null, NPC: false, 범인: false, 서사_부분수: 2 }];
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 1" }));
      await pickCard("1차 조사");
      expect(editor().getByRole("group", { name: "1차 조사 수정" })).toBeInTheDocument();
      expect(editor().queryByText("개인 서사 공개")).not.toBeInTheDocument();
    });

    it("고른 진행단계를 삭제하면 확인 없이 바로 지우고 수정 항목이 사라진다(복사·떼기 버튼은 없다)", async () => {
      routes["DELETE /api/works/7/content/phase-steps/9"] = () => new Response(null, { status: 204 });
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 1" }));
      await pickCard("1차 조사");
      expect(editor().queryByRole("button", { name: /복사|떼기/ })).not.toBeInTheDocument();
      await userEvent.click(editor().getByRole("button", { name: "1차 조사 삭제" }));
      await waitFor(() => expect(sent("DELETE /api/works/7/content/phase-steps/9")).toHaveLength(1));
      await waitFor(() => expect(editor().queryByRole("group", { name: "1차 조사 수정" })).not.toBeInTheDocument());
    });

    it("JSON 이 객체가 아니면 저장하지 않는다", async () => {
      renderApp("/works/7?tab=phases");
      await userEvent.click(await screen.findByRole("listitem", { name: "페이즈 1" }));
      await pickCard("1차 조사");
      const box = within(editor().getByRole("group", { name: "1차 조사 수정" }));
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
    routes["POST /api/scripts/check"] = () => json({ 정상: true, 오류: null, 줄: null, 함수: [] });
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

  it("스크립트를 입력하면 검사 결과를 보여 주고, 오류가 있으면 만들 수 없다", async () => {
    routes["POST /api/library/phases"] = () => json(item({ 버전: 3 }), 201);
    routes["POST /api/scripts/check"] = async (req) => {
      const { 스크립트 } = (await req.json()) as { 스크립트: string };
      return json(스크립트.includes("몰라") ? { 정상: false, 오류: "알 수 없는 이름 '몰라'", 줄: 2, 함수: [] } : { 정상: true, 오류: null, 줄: null, 함수: ["실행"] });
    };
    renderApp("/make/library");
    const form = await screen.findByRole("form", { name: "진행단계 만들기" });
    await userEvent.type(within(form).getByLabelText("이름"), "새 카드");
    const editor = within(form).getByLabelText("스크립트");
    await userEvent.click(editor);
    await userEvent.paste("def 실행(카드):\n    몰라()");
    expect(await within(form).findByText(/2번째 줄: 알 수 없는 이름/)).toBeInTheDocument();
    expect(within(form).getByRole("button", { name: "만들기" })).toBeDisabled();
    await userEvent.clear(editor);
    await userEvent.click(editor);
    await userEvent.paste("def 실행(카드):\n    pass");
    expect(await within(form).findByText(/검사 통과 · 정의한 함수: 실행/)).toBeInTheDocument();
    await waitFor(() => expect(within(form).getByRole("button", { name: "만들기" })).toBeEnabled());
    await userEvent.click(within(form).getByRole("button", { name: "만들기" }));
    await waitFor(() => expect(sent("POST /api/library/phases")).toHaveLength(1));
    expect(await sent("POST /api/library/phases")[0].req.json()).toMatchObject({ 이름: "새 카드", 규칙: { 스크립트: "def 실행(카드):\n    pass" } });
  });

  it("스크립트가 있는 버전으로 새 버전을 만들면 스크립트가 입력칸으로 옮겨진다", async () => {
    routes["GET /api/library/phases"] = () => json([item({ 규칙: { 스크립트: "def 실행(카드):\n    pass", 시간: 5 } })]);
    renderApp("/make/library");
    await userEvent.click(await screen.findByRole("button", { name: "이 버전으로 새 버전 만들기" }));
    const form = screen.getByRole("form", { name: "진행단계 만들기" });
    expect(within(form).getByLabelText("스크립트")).toHaveValue("def 실행(카드):\n    pass");
    expect(within(form).getByLabelText("규칙 (JSON)")).toHaveValue('{"시간":5}');
  });

  it("운영자에게는 '공통 항목으로 만들기' 선택이 보인다", async () => {
    routes["GET /api/auth/me"] = () => json({ ...account, 권한: "운영자" });
    renderApp("/make/library");
    expect((await screen.findAllByLabelText(/공통 항목으로 만들기/)).length).toBeGreaterThan(0);
  });
});
