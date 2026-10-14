"""공개/비공개 전환 규칙 (DB_RULES B35)."""
import pytest

from app.visibility import actor_level, publish_denied_reason


# ---- 규칙 자체 (순수 함수) --------------------------------------------------------------

@pytest.mark.parametrize("role,owner,expected", [
    ("사용자", True, "제작자"), ("사용자", False, None),
    ("관리자", False, "관리자"), ("관리자", True, "관리자"),
    ("운영자", False, "운영자"), ("운영자", True, "운영자"),
])
def test_actor_level(role, owner, expected):
    assert actor_level(role, owner) == expected


# (공개권한, 요청자 권한, 소유자 여부) -> 공개 가능?
PUBLISH_MATRIX = [
    ("제작자", "사용자", True, True),
    ("제작자", "관리자", False, False),   # 제작자가 비공개한 작품은 관리자도 공개할 수 없다
    ("제작자", "운영자", False, False),   # 운영자도 마찬가지
    ("제작자", "관리자", True, True),     # 관리자 권한을 가진 제작자는 제작자로서 공개할 수 있다
    ("관리자", "사용자", True, False),    # 관리자가 비공개한 작품은 제작자가 공개할 수 없다
    ("관리자", "관리자", False, True),
    ("관리자", "운영자", False, True),
    ("운영자", "사용자", True, False),
    ("운영자", "관리자", False, False),   # 운영자가 비공개한 작품은 관리자가 공개할 수 없다
    ("운영자", "운영자", False, True),
    ("관리자", "사용자", False, False),   # 남은 아무 권한도 없다
]


@pytest.mark.parametrize("right,role,owner,allowed", PUBLISH_MATRIX)
def test_publish_rule_matrix(right, role, owner, allowed):
    reason = publish_denied_reason(right, actor_level(role, owner), owner)
    assert (reason is None) is allowed


# ---- API ------------------------------------------------------------------------------

@pytest.fixture
def work_of(client):
    def make(owner):
        return client.post("/api/works", headers=owner.headers, json={"제목": "저택의 비밀"}).json()["번호"]
    return make


def post(client, who, wid, action):
    return client.post(f"/api/works/{wid}/{action}", headers=who.headers)


def state(client, who, wid):
    body = client.get(f"/api/works/{wid}", headers=who.headers).json()
    return body["공개여부"], body["공개권한"]


def test_new_work_is_private_and_owner_can_publish_and_unpublish(client, make_account, work_of):
    owner = make_account()
    wid = work_of(owner)
    assert state(client, owner, wid) == (False, "제작자")
    assert post(client, owner, wid, "publish").status_code == 200
    assert state(client, owner, wid) == (True, "제작자")
    assert post(client, owner, wid, "unpublish").json()["공개권한"] == "제작자"
    assert post(client, owner, wid, "publish").status_code == 200


def test_admin_cannot_publish_work_before_owner_ever_published(client, make_account, work_of):
    owner, admin, operator = make_account(), make_account("관리자"), make_account("운영자")
    wid = work_of(owner)
    assert post(client, admin, wid, "publish").status_code == 403
    assert post(client, operator, wid, "publish").status_code == 403


def test_admin_unpublishes_public_work_and_owner_cannot_republish(client, make_account, work_of):
    owner, admin = make_account(), make_account("관리자")
    wid = work_of(owner)
    post(client, owner, wid, "publish")
    res = post(client, admin, wid, "unpublish")  # 남의 작품이어도 관리자는 비공개 처리할 수 있다
    assert res.status_code == 200 and (res.json()["공개여부"], res.json()["공개권한"]) == (False, "관리자")
    assert post(client, owner, wid, "publish").status_code == 403
    assert state(client, owner, wid) == (False, "관리자")


def test_admin_locked_work_can_be_published_by_admin_or_operator(client, make_account, work_of):
    owner, admin, admin2, operator = make_account(), make_account("관리자"), make_account("관리자"), make_account("운영자")
    wid = work_of(owner)
    post(client, owner, wid, "publish")
    post(client, admin, wid, "unpublish")
    assert post(client, admin2, wid, "publish").status_code == 200  # 다른 관리자도 공개 가능
    post(client, admin, wid, "unpublish")
    assert post(client, operator, wid, "publish").status_code == 200  # 운영자도 공개 가능


def test_operator_locked_work_can_only_be_published_by_operator(client, make_account, work_of):
    owner, admin, operator = make_account(), make_account("관리자"), make_account("운영자")
    wid = work_of(owner)
    post(client, owner, wid, "publish")
    assert post(client, operator, wid, "unpublish").json()["공개권한"] == "운영자"
    assert post(client, owner, wid, "publish").status_code == 403
    assert post(client, admin, wid, "publish").status_code == 403
    assert post(client, operator, wid, "publish").status_code == 200


def test_owner_unpublish_locks_out_admin_and_operator(client, make_account, work_of):
    owner, admin, operator = make_account(), make_account("관리자"), make_account("운영자")
    wid = work_of(owner)
    post(client, owner, wid, "publish")
    post(client, owner, wid, "unpublish")
    assert post(client, admin, wid, "publish").status_code == 403
    assert post(client, operator, wid, "publish").status_code == 403
    assert post(client, owner, wid, "publish").status_code == 200


def test_return_publish_right_to_owner_lets_owner_republish(client, make_account, work_of):
    owner, admin, operator = make_account(), make_account("관리자"), make_account("운영자")
    wid = work_of(owner)
    post(client, owner, wid, "publish")
    post(client, admin, wid, "unpublish")
    assert post(client, owner, wid, "return-to-owner").status_code == 403  # 제작자는 스스로 되찾을 수 없다
    res = post(client, admin, wid, "return-to-owner")
    assert res.status_code == 200 and res.json()["공개권한"] == "제작자"
    assert post(client, owner, wid, "publish").status_code == 200


def test_operator_lock_can_only_be_returned_by_operator(client, make_account, work_of):
    owner, admin, operator = make_account(), make_account("관리자"), make_account("운영자")
    wid = work_of(owner)
    post(client, owner, wid, "publish")
    post(client, operator, wid, "unpublish")
    assert post(client, admin, wid, "return-to-owner").status_code == 403
    assert post(client, operator, wid, "return-to-owner").status_code == 200
    assert state(client, owner, wid) == (False, "제작자")


def test_state_conflicts(client, make_account, work_of):
    owner, admin = make_account(), make_account("관리자")
    wid = work_of(owner)
    assert post(client, owner, wid, "unpublish").status_code == 409          # 이미 비공개
    assert post(client, owner, wid, "return-to-owner").status_code == 409    # 이미 제작자에게 있음
    post(client, owner, wid, "publish")
    assert post(client, owner, wid, "publish").status_code == 409            # 이미 공개
    assert post(client, admin, wid, "return-to-owner").status_code == 409    # 공개 중


def test_unrelated_user_sees_nothing(client, make_account, work_of):
    owner, stranger = make_account(), make_account()
    wid = work_of(owner)
    for action in ("publish", "unpublish", "return-to-owner"):
        assert post(client, stranger, wid, action).status_code == 404
    assert post(client, owner, 999999, "publish").status_code == 404


def test_admin_gets_no_other_access_to_the_work(client, make_account, work_of):
    owner, admin = make_account(), make_account("관리자")
    wid = work_of(owner)
    # 공개 상태를 바꾸는 권한만 있다. 작품 내용 조회·수정·인물 접근은 여전히 제작자만.
    assert client.get(f"/api/works/{wid}", headers=admin.headers).status_code == 404
    assert client.patch(f"/api/works/{wid}", headers=admin.headers, json={"제목": "x"}).status_code == 404
    assert client.get(f"/api/works/{wid}/characters", headers=admin.headers).status_code == 404
    assert client.get("/api/works", headers=admin.headers).json() == []


def test_requires_login(client):
    assert client.post("/api/works/1/publish").status_code == 401
