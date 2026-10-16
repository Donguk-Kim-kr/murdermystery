import { Link } from "react-router-dom";

import { SPACES } from "../spaces";

/** 제작공간: 게임 만들기와 라이브러리 만들기(진행단계·기믹) 두 갈래. */
export function MakeHubPage() {
  return (
    <main className="page">
      <div className="page-head">
        <h1>{SPACES.make}</h1>
      </div>
      <div className="hub">
        <Link to="/make/games" className="hub-card">
          <h2>게임 만들기</h2>
          <p>게임 흐름을 짜고, 카드를 배치해 세부 내용을 채웁니다.</p>
        </Link>
        <Link to="/make/library" className="hub-card">
          <h2>라이브러리 만들기</h2>
          <p>게임에 가져다 쓸 진행단계와 기믹을 만듭니다.</p>
        </Link>
      </div>
    </main>
  );
}
