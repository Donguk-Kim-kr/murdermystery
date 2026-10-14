// 서버 규칙(backend/app/visibility.py, DB_RULES B35)을 화면 표시용으로 옮긴 것이다.
// 실제 허용 여부는 서버가 판단하며, 여기서는 어떤 버튼을 보여 줄지만 정한다.
export type Level = "제작자" | "관리자" | "운영자";
export type Role = "사용자" | "관리자" | "운영자";

const RANK: Record<Level, number> = { 제작자: 1, 관리자: 2, 운영자: 3 };

/** 자기 작품을 볼 때의 단계. 항상 제작자 자격이고, 운영자만 예외로 운영자다. */
export function levelOnOwnWork(role: Role): Level {
  return role === "운영자" ? "운영자" : "제작자";
}

/** 비공개 작품을 이 단계가 공개할 수 있는가. 자기 작품 화면만 있으므로 제작자 여부는 항상 참이다. */
export function canPublish(right: Level, level: Level): boolean {
  return right === "제작자" || RANK[level] >= RANK[right];
}
