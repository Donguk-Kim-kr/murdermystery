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
    expect(screen.getByText(/선택을 확정했습니다\. 다음 단계로 넘어가기 전에는 취소하고 다시 고를 수 있습니다/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /의사/ })).toBeDisabled();
  });

  it("확정한 뒤에는 선택 취소 버튼으로 서버에 취소를 보낸다", async () => {
    posts.length = 0;
    state = makeState({ 나: { ...state.나, 인물_순서: 11 }, 화면: [{ ...choice(), 내_선택_끝남: true, 항목: [{ ...choice().항목[0], 선택한_계정: 1 }, { ...choice().항목[1] }] }] });
    render(<GamePage />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "선택 취소" }));
    await waitFor(() => expect(posts).toEqual([{ path: "/api/game/me/answer", body: { 질문ID: "1:5:확인", 값: "취소" } }]));
  });

  it("카드 설정이 켜져 있으면 인물 카드에 선택 화면 소개가 보인다", async () => {
    state = makeState({ 화면: [{ ...choice(), 항목: [{ ...choice().항목[0], 선택소개: "마을의 다정한 의사" }, { ...choice().항목[1] }] }] });
    render(<GamePage />);
    expect(await screen.findByText("마을의 다정한 의사")).toBeInTheDocument();
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

  it("입력 블록은 글자를 쓰고 보내기를 눌러야 서버로 보내고, 글자 수를 넘으면 보낼 수 없다", async () => {
    const input = { 종류: "입력", 이름: "한 줄 답변", 질문: "범인은 누구입니까?", 글자수: 5, 질문ID: "1:5:한 줄 답변" };
    state = makeState({ 화면: [input] });
    render(<GamePage />);
    const user = userEvent.setup();
    const send = await screen.findByRole("button", { name: "보내기" });
    expect(send).toBeDisabled();
    const box = screen.getByLabelText("범인은 누구입니까?");
    await user.type(box, "여섯글자예요");
    expect(screen.getByText("6/5자")).toHaveClass("error");
    expect(send).toBeDisabled();
    await user.clear(box);
    await user.type(box, "집사");
    await user.click(send);
    await waitFor(() => expect(posts).toEqual([{ path: "/api/game/me/answer", body: { 질문ID: "1:5:한 줄 답변", 값: "집사" } }]));
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
    handlers["/api/rooms/me/start"] = () => json({ detail: "플레이어 수(1명)가 허용 인원(2명)이어야 시작할 수 있습니다" }, 409);
    mountRoom(() => room());
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "게임 시작" }));
    expect(posts.at(-1)?.path).toBe("/api/rooms/me/start");
    expect(await screen.findByRole("alert")).toHaveTextContent("허용 인원(2명)");
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

describe("조사 블록", () => {
  const places = (disabled: boolean) => ({
    종류: "선택지", 이름: "조사할 장소", 한사람당: 1, 확인필요: false, 질문ID: "1:5:확인", 내_선택_끝남: false,
    항목: [
      { 값: 2, 이름: "저택 › 서재", 유형: null, 특징: "책이 많다", 비활성: false },
      { 값: 3, 이름: "정원", 유형: "야외", 특징: null, 비활성: disabled },
    ],
  });

  it("장소를 누르면 확인 없이 바로 보내고, 얻을 것이 없는 장소는 누를 수 없다", async () => {
    state = makeState({ 화면: [places(true)] });
    render(<GamePage />);
    const user = userEvent.setup();
    expect(await screen.findByRole("button", { name: /정원/ })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "확인" })).toBeNull();
    await user.click(screen.getByRole("button", { name: /저택 › 서재/ }));
    await waitFor(() => expect(posts).toEqual([{ path: "/api/game/me/answer", body: { 질문ID: "1:5:확인", 값: 2 } }]));
  });

  it("캐릭터를 이미 정한 플레이어도 장소를 고를 수 있다", async () => {
    state = makeState({ 나: { 계정_번호: 1, 역할: "플레이어", 인물_순서: 11, 방장: true, 진행_권한: true }, 화면: [places(false)] });
    render(<GamePage />);
    expect(await screen.findByRole("button", { name: /정원/ })).toBeEnabled();
  });

  it("내 단서 탭에 단서와 증언 카드가 장소와 함께 보인다", async () => {
    state = makeState({
      화면: [],
      탭: [{
        종류: "카드목록", 이름: "내 단서", 카드: "조사",
        항목: [
          { 종류: "단서", 이름: "찢어진 편지", 공개이름: "서랍 속 종이", 내용: "편지 내용", 장소: "저택 › 서재" },
          { 종류: "증언", 이름: "집사의 증언", 공개이름: "집사", 내용: "저는 보았습니다", 장소: "저택 › 주방" },
        ],
      }],
    });
    render(<GamePage />);
    await userEvent.setup().click(await screen.findByRole("tab", { name: "내 단서" }));
    const list = screen.getByRole("region", { name: "내 단서" });
    expect(within(list).getByText("서랍 속 종이")).toBeInTheDocument();                       // 남들에게 보이는 이름
    expect(within(list).getByText("찢어진 편지")).toBeInTheDocument();                       // 진짜 이름이 그 아래에 있다
    expect(within(list).getByText("저택 › 주방")).toBeInTheDocument();
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).queryByText("편지 내용")).not.toBeInTheDocument();                   // 내용은 눌러야 펼쳐진다
    await userEvent.setup().click(within(list).getByRole("button", { name: /서랍 속 종이/ }));
    expect(within(list).getByText("편지 내용")).toBeInTheDocument();
  });

  it("공개이름이 없으면 이름 하나만 보인다", async () => {
    state = makeState({ 탭: [{ 종류: "카드목록", 이름: "내 단서", 카드: "조사", 항목: [{ 종류: "단서", 이름: "찢어진 편지", 내용: "편지 내용", 장소: "서재" }] }] });
    render(<GamePage />);
    await userEvent.setup().click(await screen.findByRole("tab", { name: "내 단서" }));
    expect(screen.getAllByText("찢어진 편지")).toHaveLength(1);
  });

  it("얻은 것이 없으면 안내한다", async () => {
    state = makeState({ 탭: [{ 종류: "카드목록", 이름: "내 단서", 카드: "조사", 항목: [] }] });
    render(<GamePage />);
    await userEvent.setup().click(await screen.findByRole("tab", { name: "내 단서" }));
    expect(screen.getByText("아직 얻은 것이 없습니다.")).toBeInTheDocument();
  });
});

describe("단서 보여 주기·양도", () => {
  const me = { 계정_번호: 1, 역할: "플레이어", 인물_순서: 10, 방장: true, 진행_권한: true } as const;
  const base = () => ({
    나: me,
    플레이어: [
      { 계정_번호: 1, 닉네임: "탐정", 인물_순서: 10, 인물_이름: "의사", 접속중: true },
      { 계정_번호: 2, 닉네임: "조수", 인물_순서: 11, 인물_이름: "집사", 접속중: true },
      { 계정_번호: 3, 닉네임: "하녀", 인물_순서: 12, 인물_이름: "하녀", 접속중: true },
    ],
  });
  const tabWith = (items: unknown[], extra: Record<string, unknown> = {}) => ({
    종류: "카드목록", 이름: "내 단서", 카드: "토론", 동작: ["보여주기", "양도"], 질문ID: "1:5:내 단서", 항목: items, ...extra,
  });
  const clue = { 종류: "단서", 순서: 4, 이름: "찢어진 편지", 내용: "편지 내용", 장소: "저택 › 서재", 양도가능: true, 공개: [] as unknown };
  const testimony = { 종류: "증언", 순서: 1, 이름: "집사의 증언", 내용: "봤습니다", 장소: "주방", 양도가능: false };

  async function openTab() {
    render(<GamePage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "내 단서" }));
    return user;
  }

  it("단서 카드에는 보여 주기·양도 버튼이 있고 증언에는 없다", async () => {
    state = makeState({ ...base(), 탭: [tabWith([clue, testimony])] });
    await openTab();
    const cards = screen.getAllByRole("listitem");
    expect(within(cards[0]).getByRole("button", { name: "보여 주기" })).toBeInTheDocument();
    expect(within(cards[0]).getByRole("button", { name: "양도" })).toBeInTheDocument();
    expect(within(cards[1]).queryByRole("button", { name: "보여 주기" })).toBeNull();
    expect(within(cards[1]).queryByRole("button", { name: "양도" })).toBeNull();
    expect(within(cards[0]).getByText("공개하지 않음")).toBeInTheDocument();
  });

  it("여러 명을 골라 보여 주면 대상 목록으로 보내고, 모두를 고르면 전체로 보낸다", async () => {
    state = makeState({ ...base(), 탭: [tabWith([clue])] });
    const user = await openTab();
    await user.click(screen.getByRole("button", { name: "보여 주기" }));
    await user.click(screen.getByRole("checkbox", { name: "조수" }));
    await user.click(screen.getByRole("checkbox", { name: "하녀" }));
    await user.click(screen.getByRole("button", { name: "적용" }));
    await waitFor(() => expect(posts.at(-1)).toEqual({ path: "/api/game/me/answer", body: { 질문ID: "1:5:내 단서", 값: { 동작: "보여주기", 단서: 4, 대상: [2, 3] } } }));
    await user.click(screen.getByRole("button", { name: "보여 주기" }));
    await user.click(screen.getByRole("checkbox", { name: "모두" }));
    await user.click(screen.getByRole("button", { name: "적용" }));
    await waitFor(() => expect(posts.at(-1)?.body).toEqual({ 질문ID: "1:5:내 단서", 값: { 동작: "보여주기", 단서: 4, 대상: "전체" } }));
  });

  it("지금 공개 중인 대상이 미리 골라져 있고, 모두 해제하고 적용하면 취소다", async () => {
    state = makeState({ ...base(), 탭: [tabWith([{ ...clue, 공개: [2] }])] });
    const user = await openTab();
    expect(screen.getByText("공개 대상: 조수")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "보여 주기" }));
    expect(screen.getByRole("checkbox", { name: "조수" })).toBeChecked();
    await user.click(screen.getByRole("checkbox", { name: "조수" }));
    await user.click(screen.getByRole("button", { name: "적용" }));
    await waitFor(() => expect(posts.at(-1)?.body).toEqual({ 질문ID: "1:5:내 단서", 값: { 동작: "보여주기", 단서: 4, 대상: [] } }));
  });

  it("양도는 한 명을 골라야 보낼 수 있다", async () => {
    state = makeState({ ...base(), 탭: [tabWith([clue])] });
    const user = await openTab();
    await user.click(screen.getByRole("button", { name: "양도" }));
    const send = screen.getByRole("button", { name: "넘기기" });
    expect(send).toBeDisabled();
    expect(screen.queryByRole("radio", { name: "탐정" })).toBeNull();           // 나 자신은 고를 수 없다
    await user.click(screen.getByRole("radio", { name: "하녀" }));
    await user.click(send);
    await waitFor(() => expect(posts.at(-1)?.body).toEqual({ 질문ID: "1:5:내 단서", 값: { 동작: "양도", 단서: 4, 대상: [3] } }));
  });

  it("동작이 없는 탭(지난 단계에서 남은 것)에는 버튼이 없다", async () => {
    state = makeState({ ...base(), 탭: [tabWith([clue], { 동작: undefined, 질문ID: undefined })] });
    await openTab();
    expect(screen.queryByRole("button", { name: "보여 주기" })).toBeNull();
    expect(screen.getByText("찢어진 편지")).toBeInTheDocument();
  });

  it("다른 사람이 보여 준 단서에는 보여 준 사람이 표시된다", async () => {
    state = makeState({ ...base(), 탭: [{ 종류: "카드목록", 이름: "공개된 단서", 카드: "토론", 항목: [{ ...clue, 공개: undefined, 주인: "집사 (조수)" }] }] });
    render(<GamePage />);
    await userEvent.setup().click(await screen.findByRole("tab", { name: "공개된 단서" }));
    expect(screen.getByText("집사 (조수)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "양도" })).toBeNull();
  });
});

describe("투표 블록", () => {
  const box = (over: Record<string, unknown> = {}) => ({
    종류: "투표", 이름: "최종 투표", 질문: "범인은 누구입니까?", 질문ID: "1:7:최종 투표", 내_선택: null, 투표수: 0,
    항목: [
      { 값: 10, 이름: "의사", 직업: "의사", 나이: 40, 성별: null, 비활성: true },       // 내 인물
      { 값: 11, 이름: "집사", 직업: "집사", 나이: 60, 성별: null, 비활성: false },
      { 값: 12, 이름: "하녀", 직업: "하녀", 나이: 20, 성별: null, 비활성: false },
    ],
    ...over,
  });

  it("후보를 고르고 투표를 눌러야 보내고, 내 인물은 고를 수 없다", async () => {
    state = makeState({ 화면: [box()] });
    render(<GamePage />);
    const user = userEvent.setup();
    const send = await screen.findByRole("button", { name: "투표" });
    expect(send).toBeDisabled();
    expect(screen.getByRole("button", { name: /의사/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /집사/ }));
    expect(posts).toEqual([]);
    await user.click(send);
    await waitFor(() => expect(posts).toEqual([{ path: "/api/game/me/answer", body: { 질문ID: "1:7:최종 투표", 값: 11 } }]));
  });

  it("투표한 뒤에는 내 투표가 표시되고 다른 후보로 바꿀 수 있다", async () => {
    state = makeState({ 화면: [box({ 내_선택: 11 })] });
    render(<GamePage />);
    const user = userEvent.setup();
    expect(await screen.findByText("내 투표")).toBeInTheDocument();
    expect(screen.getByText(/집사에게 투표했습니다/)).toBeInTheDocument();
    const change = screen.getByRole("button", { name: "투표 바꾸기" });
    expect(change).toBeDisabled();                                         // 같은 후보로는 바꿀 수 없다
    await user.click(screen.getByRole("button", { name: /하녀/ }));
    await user.click(change);
    await waitFor(() => expect(posts.at(-1)?.body).toEqual({ 질문ID: "1:7:최종 투표", 값: 12 }));
  });

  it("인물이 아닌 후보(사고사)에도 투표할 수 있고 인물 정보는 보이지 않는다", async () => {
    state = makeState({
      화면: [box({ 항목: [
        { 값: 11, 이름: "집사", 직업: "집사", 나이: 60, 성별: null, 비활성: false, 기타: false },
        { 값: "사고사", 이름: "사고사", 직업: null, 나이: null, 성별: null, 비활성: false, 기타: true },
      ] })],
    });
    render(<GamePage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /사고사/ }));
    await user.click(screen.getByRole("button", { name: "투표" }));
    await waitFor(() => expect(posts.at(-1)?.body).toEqual({ 질문ID: "1:7:최종 투표", 값: "사고사" }));
  });

  it("관전자는 투표할 수 없다", async () => {
    state = makeState({ 나: { 계정_번호: 9, 역할: "관전자", 인물_순서: null, 방장: false, 진행_권한: false }, 화면: [box()] });
    render(<GamePage />);
    await screen.findByText("관전 중에는 투표할 수 없습니다.");
    expect(screen.queryByRole("button", { name: "투표" })).toBeNull();
    expect(screen.getByRole("button", { name: /집사/ })).toBeDisabled();
  });
});

describe("단계가 바뀔 때", () => {
  it("읽던 탭에서 현재 화면으로 돌아온다", async () => {
    state = makeState({
      화면: [{ 종류: "글", 이름: "안내", 내용: "현재 안내" }],
      탭: [{ 종류: "글", 이름: "공통 스토리", 내용: "프롤로그 내용", 카드: "프롤로그" }],
    });
    render(<GamePage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "공통 스토리" }));
    expect(screen.queryByText("현재 안내")).toBeNull();
    await waitFor(() => expect(events).not.toBeNull());
    state = makeState({
      상태_버전: 4, 페이즈: { 위치: 2, 전체: 3, 순서: 2, 이름: "다음 단계", 진행시간: 0 },
      화면: [{ 종류: "글", 이름: "안내", 내용: "다음 단계 안내" }],
      탭: [{ 종류: "글", 이름: "공통 스토리", 내용: "프롤로그 내용", 카드: "프롤로그" }],
    });
    push(4);
    expect(await screen.findByText("다음 단계 안내")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "현재 화면" })).toHaveAttribute("aria-selected", "true");
  });
});
