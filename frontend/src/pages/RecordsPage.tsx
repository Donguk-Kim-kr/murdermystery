import { SPACES } from "../spaces";

/** 기록공간: 내가 플레이한 게임의 기록. 게임 진행 기능이 아직 없어 기록이 쌓이지 않는다. */
export function RecordsPage() {
  return (
    <main className="page">
      <div className="page-head">
        <h1>{SPACES.records}</h1>
      </div>
      <div className="empty">
        <strong>아직 기록이 없습니다.</strong>
        <p>플레이한 게임의 캐릭터, 엔딩, 평점과 후기가 여기에 쌓입니다. (게임 진행 기능은 아직 만들지 않았습니다)</p>
      </div>
    </main>
  );
}
