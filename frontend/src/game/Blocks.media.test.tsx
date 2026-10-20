import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { BlockView, type Block } from "./Blocks";
import type { GameState } from "./useGame";

afterEach(cleanup);

const state = {
  나: { 계정_번호: 1, 역할: "플레이어", 인물_순서: null, 방장: false, 진행_권한: false, 관전방식: null },
  플레이어: [{ 계정_번호: 1, 닉네임: "나", 인물_순서: null, 인물_이름: null, 접속중: true }],
} as unknown as GameState;

const view = (block: Block) => render(<BlockView block={block} state={state} onAnswer={async () => true} />);

describe("이미지·영상 표시", () => {
  it("공통 스토리 글 위에 영상 재생기가 나온다(주소가 없으면 나오지 않는다)", () => {
    const { container, rerender } = view({ 종류: "글", 이름: "공통 스토리", 내용: "이야기", 영상: "/api/media/v.mp4?a=1&e=2&s=3" });
    const video = container.querySelector("video")!;
    expect(video).toHaveAttribute("src", "/api/media/v.mp4?a=1&e=2&s=3");
    expect(video).toHaveAttribute("controls");
    expect(screen.getByText("이야기")).toBeInTheDocument();
    rerender(<BlockView block={{ 종류: "글", 이름: "공통 스토리", 내용: "이야기" }} state={state} onAnswer={async () => true} />);
    expect(container.querySelector("video")).toBeNull();
  });

  it("캐릭터 선택 카드에 이미지가 붙은 인물만 이미지가 나온다", () => {
    view({
      종류: "선택지", 이름: "캐릭터 선택", 질문ID: "q", 확인필요: true,
      항목: [
        { 값: 1, 이름: "황칠성", 직업: "사장", 이미지: "/api/media/a.jpg?a=1&e=2&s=3", 선택한_계정: null },
        { 값: 2, 이름: "한유진", 직업: "교사", 선택한_계정: null },
      ],
    });
    expect(screen.getByAltText("황칠성 이미지")).toHaveAttribute("src", "/api/media/a.jpg?a=1&e=2&s=3");
    expect(screen.queryByAltText("한유진 이미지")).not.toBeInTheDocument();
  });

  it("단서 카드의 이미지는 카드를 펼쳤을 때 내용과 함께 보인다", async () => {
    view({
      종류: "카드목록", 이름: "내 단서",
      항목: [
        { 종류: "단서", 순서: 1, 이름: "찢어진 편지", 공개이름: "서랍 속 종이", 내용: "편지 내용", 장소: "서재", 이미지: "/api/media/c.png?a=1&e=2&s=3" },
        { 종류: "단서", 순서: 2, 이름: "깨진 안경", 내용: "안경 내용", 장소: "서재" },
      ],
    });
    expect(screen.queryByAltText("서랍 속 종이 이미지")).not.toBeInTheDocument();                 // 접혀 있을 때는 내용도 이미지도 보이지 않는다
    await userEvent.click(screen.getByRole("button", { name: /서랍 속 종이/ }));
    expect(screen.getByAltText("서랍 속 종이 이미지")).toHaveAttribute("src", "/api/media/c.png?a=1&e=2&s=3");
    expect(screen.getByText("편지 내용")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /깨진 안경/ }));
    expect(screen.getByText("안경 내용")).toBeInTheDocument();
    expect(screen.queryByAltText("깨진 안경 이미지")).not.toBeInTheDocument();
  });
});
