"""작품 공개 규칙 (docs/DB_RULES.md B35). DB 접근 없는 순수 함수만 둔다.

* 요청자의 단계(level)는 `운영자` > `관리자` > `제작자` 중 가장 높은 것이다.
  운영자·관리자는 서버 전체 권한(계정.권한)이고, 제작자는 해당 작품의 `계정_번호`와 같을 때만 성립한다.
* 공개 중인 작품은 제작자·관리자·운영자 누구나 비공개로 바꿀 수 있고, 그때 `공개권한`이 바꾼 사람의 단계가 된다.
* 비공개 작품은 `공개권한`을 가진 쪽만 공개할 수 있다.
    - 제작자: 제작자만 (관리자·운영자도 공개할 수 없다)
    - 관리자: 관리자·운영자
    - 운영자: 운영자만
* 관리자·운영자는 자기가 비공개한 작품의 공개권한을 제작자에게 돌려줄 수 있다 ("수정해서 다시 공개하세요").
"""
from typing import Literal

Level = Literal["제작자", "관리자", "운영자"]
RANK: dict[str, int] = {"제작자": 1, "관리자": 2, "운영자": 3}


def actor_level(role: str, is_owner: bool) -> Level | None:
    """서버 권한과 작품 소유 여부로 이 작품에 대한 요청자의 단계를 구한다. 관계가 없으면 None."""
    if role == "운영자":
        return "운영자"
    if role == "관리자":
        return "관리자"
    return "제작자" if is_owner else None


def publish_denied_reason(right: str, level: Level | None, is_owner: bool) -> str | None:
    """공개할 수 없으면 사유를, 가능하면 None 을 돌려준다."""
    if level is None:
        return "이 작품에 대한 권한이 없습니다"
    if right == "제작자":
        return None if is_owner else "제작자가 비공개했거나 아직 공개 전인 작품은 제작자만 공개할 수 있습니다"
    if RANK[level] >= RANK[right]:
        return None
    if right == "관리자":
        return "관리자가 비공개 처리한 작품입니다. 관리자 이상만 공개할 수 있습니다"
    return "운영자가 비공개 처리한 작품입니다. 운영자만 공개할 수 있습니다"
