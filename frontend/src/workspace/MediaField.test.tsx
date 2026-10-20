import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { answerConfirm } from "../confirmTest";
import { ConfirmProvider } from "../confirm/ConfirmContext";
import { MediaField, resetMediaCache, type MediaItem } from "./MediaField";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

let items: MediaItem[];
let calls: { method: string; path: string; type: string | null; size: number | null }[];
let failUpload: { status: number; detail: string } | null;

beforeEach(() => {
  items = [];
  calls = [];
  failUpload = null;
  resetMediaCache();
  vi.stubGlobal("fetch", async (input: Request) => {
    const url = new URL(input.url);
    const size = input.method === "PUT" ? (await input.clone().blob()).size : null;
    calls.push({ method: input.method, path: url.pathname + url.search, type: input.headers.get("content-type"), size });
    if (input.method === "GET") return json(items);
    if (input.method === "PUT") {
      if (failUpload) return json({ detail: failUpload.detail }, failUpload.status);
      const target = url.searchParams.get("대상") as MediaItem["대상"];
      const number = url.searchParams.get("번호");
      items = [{ 순서: 1, 대상: target, 번호: number ? Number(number) : null, 유형: target === "공통스토리" ? "영상" : "이미지", 주소: "/api/media/abc.png?a=1&e=2&s=3" }];
      return json(items[0], 201);
    }
    items = items.filter((m) => !input.url.endsWith(`/media/${m.순서}`));
    return new Response(null, { status: 204 });
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const show = (props: Partial<Parameters<typeof MediaField>[0]> = {}) =>
  render(
    <ConfirmProvider>
      <MediaField workId={7} target="단서" order={2} label="단서 이미지" {...props} />
    </ConfirmProvider>,
  );
const file = (name: string, type: string, bytes = 10) => new File([new Uint8Array(bytes)], name, { type });

describe("이미지·영상 올리기", () => {
  it("붙은 것이 없으면 안내하고, 파일을 고르면 내용 그대로 올린 뒤 미리보기가 보인다", async () => {
    show();
    expect(await screen.findByText("붙은 이미지가 없습니다.")).toBeInTheDocument();
    await userEvent.upload(screen.getByLabelText("단서 이미지 파일 고르기"), file("a.png", "image/png", 321));
    const img = await screen.findByAltText("단서 이미지 미리보기");
    expect(img).toHaveAttribute("src", "/api/media/abc.png?a=1&e=2&s=3");
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.path).toBe(`/api/works/7/media?${new URLSearchParams({ 대상: "단서", 번호: "2" })}`);
    expect(put.type).toBe("image/png");
    expect(put.size).toBe(321);
  });

  it("작품에 붙은 미디어는 한 번만 불러 입력칸들이 나눠 쓴다", async () => {
    items = [{ 순서: 1, 대상: "단서", 번호: 1, 유형: "이미지", 주소: "/api/media/one.png?a=1&e=2&s=3" }];
    render(
      <ConfirmProvider>
        <MediaField workId={7} target="단서" order={1} label="단서 1 이미지" />
        <MediaField workId={7} target="단서" order={2} label="단서 2 이미지" />
      </ConfirmProvider>,
    );
    expect(await screen.findByAltText("단서 1 이미지 미리보기")).toBeInTheDocument();
    expect(screen.queryByAltText("단서 2 이미지 미리보기")).not.toBeInTheDocument();
    expect(calls.filter((c) => c.method === "GET")).toHaveLength(1);
  });

  it("공통 스토리에는 mp4 영상만 받고 영상 미리보기가 나온다", async () => {
    show({ target: "공통스토리", order: undefined, label: "공통 스토리 영상" });
    await screen.findByText("붙은 영상이 없습니다.");
    const input = screen.getByLabelText("공통 스토리 영상 파일 고르기");
    expect(input).toHaveAttribute("accept", "video/mp4");
    await userEvent.upload(input, file("v.mp4", "video/mp4"));
    expect(await screen.findByLabelText("공통 스토리 영상 미리보기")).toBeInstanceOf(HTMLVideoElement);
    expect(calls.find((c) => c.method === "PUT")!.path).toBe(`/api/works/7/media?${new URLSearchParams({ 대상: "공통스토리" })}`);
  });

  it("받지 않는 형식과 너무 큰 파일은 보내기 전에 알려 주고 서버에 보내지 않는다", async () => {
    show();
    await screen.findByText("붙은 이미지가 없습니다.");
    const input = screen.getByLabelText("단서 이미지 파일 고르기");
    await userEvent.upload(input, file("a.gif", "image/gif"), { applyAccept: false });
    expect(await screen.findByRole("alert")).toHaveTextContent("jpg·png·webp");
    await userEvent.upload(input, file("big.png", "image/png", 5 * 1024 * 1024 + 1));
    expect(await screen.findByRole("alert")).toHaveTextContent("파일이 너무 큽니다");
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
  });

  it("서버가 거절하면 그 이유를 보여 준다", async () => {
    show();
    await screen.findByText("붙은 이미지가 없습니다.");
    failUpload = { status: 415, detail: "파일 내용이 선택한 형식과 맞지 않습니다" };
    await userEvent.upload(screen.getByLabelText("단서 이미지 파일 고르기"), file("a.png", "image/png"));
    expect(await screen.findByRole("alert")).toHaveTextContent("파일 내용이 선택한 형식과 맞지 않습니다");
  });

  it("지우기는 확인을 거친다", async () => {
    items = [{ 순서: 4, 대상: "단서", 번호: 2, 유형: "이미지", 주소: "/api/media/x.png?a=1&e=2&s=3" }];
    show();
    await screen.findByAltText("단서 이미지 미리보기");
    await userEvent.click(screen.getByRole("button", { name: "지우기" }));
    expect(await answerConfirm(false)).toContain("지울까요");
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "지우기" }));
    await answerConfirm(true);
    await waitFor(() => expect(screen.queryByAltText("단서 이미지 미리보기")).not.toBeInTheDocument());
    expect(calls.find((c) => c.method === "DELETE")!.path).toBe("/api/works/7/media/4");
  });
});
