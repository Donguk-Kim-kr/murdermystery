import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RoomProvider } from "../rooms/RoomContext";
import { RoomPage } from "../pages/RoomPage";
import { GamePage } from "./GamePage";
import { createSseParser, type SseEvent } from "./sse";
import type { GameState } from "./useGame";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

function makeState(over: Partial<GameState> = {}): GameState {
  return {
    상태_버전: 1,
    화면: [],
    탭: [],
    알림: [],
    오류: [],
    종료: false,
    설정: { 자동_진행: false },
    나: { 계정_번호: 1, 역할: "플레이어", 인물_순서: null, 방장: true, 진행_권한: true },
    권한: { 계정_번호: 1, 닉네임: "탐정", 임시: false },
    시간: { 서버_시각: 0, 일시정지: false, 남은_초: null, 시간_종료: false },
    선택_완료: { 완료: 0, 전체: 2 },
    페이즈: { 위치: 1, 전체: 3, 순서: 1, 이름: "캐릭터 선택", 진행시간: 0 },
    플레이어: [
      { 계정_번호: 1, 닉네임: "탐정", 인물_순서: null, 인물_이름: null, 접속중: true },
      { 계정_번호: 2, 닉네임: "조수", 인물_순서: null, 인물_이름: null, 접속중: true },
    ],
    인물: [],
    ...over,
  } as GameState;
}

const choice = (taken: number | null = null) => ({
  종류: "선택지", 이름: "캐릭터 선택", 한사람당: 1, 확인필요: true, 질문ID: "1:5:확인", 내_선택_끝남: false, 카드: "캐릭터 선택",
  항목: [
    { 값: 10, 이름: "의사", 직업: "의사", 나이: 40, 성별: null, 선택한_계정: taken },
    { 값: 11, 이름: "집사", 직업: "집사", 나이: 60, 성별: null, 선택한_계정: null },
  ],
});

let state: GameState;
let posts: { path: string; body: unknown }[];
let handlers: Record<string, (body: unknown) => Response>;
let events: ReadableStreamDefaultController<Uint8Array> | null;
let stateReads: number;
const enc = new TextEncoder();

beforeEach(() => {
  state = makeState();
  posts = [];
  handlers = {};
  events = null;
  stateReads = 0;
  localStorage.clear();
  vi.stubGlobal("fetch", async (input: Request) => {
    const path = new URL(input.url).pathname;
    if (path === "/api/game/me/events") {
      const body = new ReadableStream<Uint8Array>({
        start(c) {
          events = c;
          c.enqueue(enc.encode(`event: version\ndata: {"상태_버전": ${state.상태_버전}}\n\n`));
        },
      });
      return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
    }
    if (input.method === "GET" && path === "/api/game/me/state") {
      stateReads += 1;
      return json(state);
    }
    if (input.method === "POST") {
      const text = await input.clone().text();
      const body = text ? JSON.parse(text) : undefined;
      posts.push({ path, body });
      const handler = handlers[path];
      if (handler) return handler(body);
      return json(state);
    }
    throw new Error(`mock 없는 요청: ${input.method} ${path}`);
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const push = (version: number) => events!.enqueue(enc.encode(`event: version\ndata: {"상태_버전": ${version}}\n\n`));

describe("SSE 해석", () => {
  const collect = () => {
    const got: SseEvent[] = [];
    return { got, feed: createSseParser((e) => got.push(e)) };
  };

  it("이벤트 이름과 데이터를 읽고 연결 유지 신호는 버린다", () => {
    const { got, feed } = collect();
    feed(': ping\n\nevent: version\ndata: {"a": 1}\n\n');
    expect(got).toEqual([{ event: "version", data: '{"a": 1}' }]);
  });

  it("줄 중간에서 끊긴 조각과 CRLF 를 이어 붙인다", () => {
    const { got, feed } = collect();
    feed("event: ver");
    feed("sion\r\ndata: 1");
    feed("23\r\n\r\ndata: 둘\n");
    feed("\n");
    expect(got).toEqual([
      { event: "version", data: "123" },
      { event: "message", data: "둘" },
    ]);
  });
});

describe("플레이 화면", () => {
  it("단계 위치와 이름, 글 블록을 보여 준다", async () => {
    state = makeState({ 화면: [{ 종류: "글", 이름: "안내", 내용: "첫 줄\n둘째 줄" }] });
    render(<GamePage />);
    expect(await screen.findByRole("heading", { name: "캐릭터 선택" })).toBeInTheDocument();
    expect(screen.getByText("1/3")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "안내" })).toHaveTextContent("첫 줄 둘째 줄");
  });

  it("인물을 고른 뒤 확인을 눌러야 서버로 보내고, 확인 전에는 바꿀 수 있다", async () => {
    state = makeState({ 화면: [choice()] });
    handlers["/api/game/me/answer"] = () => {
      state = makeState({ 상태_버전: 2, 나: { ...state.나, 인물_순서: 11 }, 화면: [{ ...choice(), 내_선택_끝남: true, 항목: [{ ...choice().항목[0] }, { ...choice().항목[1], 선택한_계정: 1 }] }] });
      return json(state);
    };
    render(<GamePage />);
    const user = userEvent.setup();
    const confirm = await screen.findByRole("button", { name: "확인" });
    expect(confirm).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /의사/ }));
    await user.click(screen.getByRole("button", { name: /집사/ }));        // 확인 전에는 다른 인물로 바꿀 수 있다
    expect(posts).toEqual([]);
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    await waitFor(() => expect(posts).toEqual([{ path: "/api/game/me/answer", body: { 질문ID: "1:5:확인", 값: 11 } }]));
    expect(await screen.findByText("내 인물")).toBeInTheDocument();
    expect(screen.getByText("선택을 확정했습니다. 바꿀 수 없습니다.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /의사/ })).toBeDisabled();
  });

  it("이미 다른 사람이 확정한 인물은 고를 수 없다", async () => {
    state = makeState({ 화면: [choice(2)] });
    render(<GamePage />);
    const taken = await screen.findByRole("button", { name: /의사/ });
    expect(taken).toBeDisabled();
    expect(within(taken).getByText("조수 선택")).toBeInTheDocument();
  });

  it("관전자는 고를 수도 확인할 수도 없다", async () => {
    state = makeState({
      나: { 계정_번호: 9, 역할: "관전자", 인물_순서: null, 방장: false, 진행_권한: false },
      화면: [choice(), { 종류: "읽기", 이름: "공통 스토리", 내용: "이야기", 질문ID: "1:4:읽기:공통 스토리", 확인필요: false, 확인함: false, 현황: { 완료: 1, 전체: 3 } }],
    });
    render(<GamePage />);
    await screen.findByText("관전 중에는 고를 수 없습니다.");
    expect(screen.queryByRole("button", { name: "확인" })).toBeNull();
    expect(screen.getByRole("button", { name: /의사/ })).toBeDisabled();
    expect(screen.getByText("확인 1/3")).toBeInTheDocument();
  });

  it("읽기 블록의 확인을 누르면 답을 보내고 현황을 보여 준다", async () => {
    const read = (done: boolean, count: number) => ({
      종류: "읽기", 이름: "공통 스토리", 내용: "모두가 읽는 이야기", 질문ID: "1:4:읽기:공통 스토리",
      확인필요: !done, 확인함: done, 현황: { 완료: count, 전체: 2 },
    });
    state = makeState({ 화면: [read(false, 0)] });
    handlers["/api/game/me/answer"] = () => (state = makeState({ 상태_버전: 2, 화면: [read(true, 1)] })) && json(state);
    render(<GamePage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "확인" }));
    expect(posts[0]).toEqual({ path: "/api/game/me/answer", body: { 질문ID: "1:4:읽기:공통 스토리", 값: true } });
    expect(await screen.findByText("확인했습니다")).toBeInTheDocument();
    expect(screen.getByText("확인 1/2")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "확인" })).toBeNull();
  });

  it("탭을 눌러 유지된 내용을 다시 읽을 수 있다", async () => {
    state = makeState({
      화면: [{ 종류: "글", 이름: "안내", 내용: "현재 안내" }],
      탭: [{ 종류: "글", 이름: "공통 스토리", 내용: "프롤로그 내용", 카드: "프롤로그" }],
    });
    render(<GamePage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "공통 스토리" }));
    expect(screen.getByText("프롤로그 내용")).toBeInTheDocument();
    expect(screen.queryByText("현재 안내")).toBeNull();
    await user.click(screen.getByRole("tab", { name: "현재 화면" }));
    expect(screen.getByText("현재 안내")).toBeInTheDocument();
  });

  it("실시간 알림이 더 새 버전을 알리면 상태를 다시 읽고, 같은 버전이면 읽지 않는다", async () => {
    render(<GamePage />);
    await screen.findByRole("heading", { name: "캐릭터 선택" });
    await waitFor(() => expect(events).not.toBeNull());
    await new Promise((r) => setTimeout(r, 30));
    const before = stateReads;
    push(1);                                                    // 이미 가진 버전이면 다시 읽지 않는다
    await new Promise((r) => setTimeout(r, 30));
    expect(stateReads).toBe(before);
    state = makeState({ 상태_버전: 5, 페이즈: { 위치: 2, 전체: 3, 순서: 2, 이름: "프로필 숙지", 진행시간: 0 } });
    push(5);
    expect(await screen.findByRole("heading", { name: "프로필 숙지" })).toBeInTheDocument();
    expect(stateReads).toBe(before + 1);
  });

  it("알림은 닫을 수 있다", async () => {
    state = makeState({ 알림: [{ 번호: 3, 글: "이미 다른 사람이 고른 인물입니다" }] });
    render(<GamePage />);
    const user = userEvent.setup();
    const note = await screen.findByRole("status");
    expect(note).toHaveTextContent("이미 다른 사람이 고른 인물입니다");
    await user.click(within(note).getByRole("button", { name: "닫기" }));
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("진행 권한이 있으면 다음 단계를 넘기고, 거부되면 이유를 보여 준다", async () => {
    handlers["/api/game/me/advance"] = () => json({ detail: "캐릭터 선택이 완료되지 않았습니다." }, 409);
    render(<GamePage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "다음 단계" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("캐릭터 선택이 완료되지 않았습니다.");
  });

  it("진행 권한이 없으면 조작 버튼 없이 누가 맡았는지 보여 준다", async () => {
    state = makeState({
      나: { 계정_번호: 2, 역할: "플레이어", 인물_순서: null, 방장: false, 진행_권한: false },
      권한: { 계정_번호: 1, 닉네임: "탐정", 임시: false },
    });
    render(<GamePage />);
    expect(await screen.findByText(/진행은 탐정님이 맡고 있습니다/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다음 단계" })).toBeNull();
  });

  it("방장은 자동 진행과 진행 맡기기를 바꿀 수 있다", async () => {
    render(<GamePage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("checkbox", { name: /자동으로 넘기기/ }));
    expect(posts.at(-1)).toEqual({ path: "/api/game/me/settings", body: { 자동_진행: true } });
    await user.selectOptions(screen.getByRole("combobox", { name: "진행 권한" }), "2");
    expect(posts.at(-1)).toEqual({ path: "/api/game/me/authority", body: { 계정_번호: 2 } });
  });

  it("게임이 없으면 안내한다", async () => {
    vi.stubGlobal("fetch", async () => json({ detail: "진행 중인 게임이 없습니다" }, 404));
    render(<GamePage />);
    expect(await screen.findByText("진행 중인 게임이 없습니다.")).toBeInTheDocument();
  });

  it("남은 시간과 시간 종료를 표시한다", async () => {
    state = makeState({ 시간: { 서버_시각: 0, 일시정지: true, 남은_초: 125, 시간_종료: false } });
    render(<GamePage />);
    expect(await screen.findByLabelText("남은 시간")).toHaveTextContent("2:05");
    expect(screen.getByText("일시정지")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "시간 다시 흐르게" })).toBeInTheDocument();
  });
});

describe("대기실에서 게임 시작", () => {
  const room = (over: Record<string, unknown> = {}) => ({
    번호: 1, 입장코드: "ABC123", 상태: "대기", 버전: "1.0", 내가_방장: true, 플레이어_수: 2, 생성일시: "2026-10-17T00:00:00",
    작품: { 번호: 7, 제목: "시험 작품", 최소인원: 2, 최대인원: 2 },
    참가자: [
      { 계정_번호: 1, 닉네임: "탐정", 방장: true, 플레이: true },
      { 계정_번호: 2, 닉네임: "조수", 방장: false, 플레이: true },
    ],
    ...over,
  });

  function mountRoom(current: () => unknown) {
    const base = globalThis.fetch;
    vi.stubGlobal("fetch", async (input: Request) => {
      const path = new URL(input.url).pathname;
      if (path === "/api/rooms/me" && input.method === "GET") return json(current());
      return base(input);
    });
    return render(
      <MemoryRouter>
        <RoomProvider>
          <RoomPage />
        </RoomProvider>
      </MemoryRouter>,
    );
  }

  it("방장은 게임 시작을 누르고, 거부 사유를 볼 수 있다", async () => {
    handlers["/api/rooms/me/start"] = () => json({ detail: "플레이어 수(1명)가 캐릭터 수(2명)와 같아야 시작할 수 있습니다" }, 409);
    mountRoom(() => room());
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "게임 시작" }));
    expect(posts.at(-1)?.path).toBe("/api/rooms/me/start");
    expect(await screen.findByRole("alert")).toHaveTextContent("캐릭터 수(2명)와 같아야");
  });

  it("방장이 아니면 시작 버튼이 없다", async () => {
    mountRoom(() => room({ 내가_방장: false }));
    await screen.findByRole("heading", { name: "시험 작품" });
    expect(screen.queryByRole("button", { name: "게임 시작" })).toBeNull();
  });

  it("방 상태가 진행으로 바뀌면 게임 화면으로 바뀐다", async () => {
    let current = room();
    mountRoom(() => current);
    await screen.findByRole("heading", { name: "시험 작품" });
    current = room({ 상태: "진행" });
    expect(await screen.findByRole("heading", { name: "캐릭터 선택" }, { timeout: 3000 })).toBeInTheDocument();
  });
});
