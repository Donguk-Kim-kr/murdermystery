/** 플레이 인원 표시: 최소와 최대가 같으면 "4명", 다르면 "2~4명". */
export function peopleText(min: number, max: number): string {
  return min === max ? `${max}명` : `${min}~${max}명`;
}
