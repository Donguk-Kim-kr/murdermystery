import { Link } from "react-router-dom";

import type { components } from "../api/schema";

type Work = components["schemas"]["WorkOut"];

/** 이 작품으로 방을 만드는 진입점. 서버가 최종 판단하므로 여기서는 막힌 이유만 미리 알려 준다. */
export function RoomPanel({ work }: { work: Work }) {
  const lockedByStaff = !work.공개여부 && work.공개권한 !== "제작자";
  const reason = !work.확정버전_있음
    ? "확정된 버전이 없어 방을 만들 수 없습니다."
    : lockedByStaff
      ? `${work.공개권한}가 비공개 처리한 작품은 공개 권한이 돌아올 때까지 방을 만들 수 없습니다.`
      : null;

  return (
    <section aria-label="방" className="card">
      <h2>방</h2>
      <p className="muted">
        이 작품으로 방을 만들어 함께 플레이합니다. 공개하지 않은 작품도 제작자와 테스터는 방을 만들 수 있고, 입장은 입장코드를
        아는 사람이면 됩니다.
      </p>
      {reason ? (
        <>
          <button type="button" disabled>방 만들기</button>
          <p className="muted">{reason}</p>
        </>
      ) : (
        <Link to={`/rooms/new/${work.번호}`} state={{ title: work.제목 }} className="button">
          이 작품으로 방 만들기
        </Link>
      )}
    </section>
  );
}
