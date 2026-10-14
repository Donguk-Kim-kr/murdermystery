"""공개/비공개 전환 규칙 (DB_RULES B35)."""
import pytest

from app.visibility import actor_level, publish_denied_reason


# ---- 규칙 자체 (순수 함수) --------------------------------------------------------------

@pytest.mark.parametrize("role,owner,expected", [
    ("사용자", True, "제작자"), ("사용자", False, None),
    ("관리자", False, "관리자"), ("관리자", True, "제작자"),  # 자기 작품에서는 제작자 자격
    ("운영자", False, "운영자"), ("운영자", True, "운영자"),
])
def test_actor_level(role, owner, expected):
    assert actor_level(role, owner) == expected


# (공개권한, 요청자 권한, 소유자 여부) -> 공개 가능?
PUBLISH_MATRIX = [
    ("제작자", "사용자", True, True),
    ("제작자", "관리자", False, False),   # 제작자가 비공개한 작품은 관리자도 공개할 수 없다
    ("제작자", "운영자", False, False),   # 운영자도 마찬가지
    ("제작자", "관리자", True, True),     # 관리자 권한을 가진 제작자도 자기 작품은 제작자로서 공개할 수 있다
    ("관리자", "관리자", True, False),    # 하지만 다른 관리자가 비공개한 자기 작품을 관리자 권한으로 공개할 수는 없다
    ("운영자", "운영자", True, True),     # 운영자는 어디서나 운영자
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
def work_of(client, confirm):
    """확정 버전이 있는 작품을 만든다 (공개하려면 확정 버전이 필요하다)."""

    def make(owner):
        wid = client.post("/api/works", headers=owner.headers, json={"제목": "저택의 비밀"}).json()["번호"]
        confirm(wid)
        return wid
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


def test_admin_who_owns_the_work_acts_as_owner(client, make_account, work_of):
    admin, other_admin = make_account("관리자"), make_account("관리자")
    wid = work_of(admin)
    assert post(client, admin, wid, "publish").status_code == 200
    res = post(client, admin, wid, "unpublish")
    assert res.json()["공개권한"] == "제작자"               # '관리자'가 아니라 제작자로 기록된다
    assert post(client, other_admin, wid, "publish").status_code == 403   # 다른 관리자는 공개할 수 없다
    assert post(client, admin, wid, "publish").status_code == 200


def test_admin_cannot_use_admin_power_on_own_work(client, make_account, work_of):
    owner_admin, other_admin = make_account("관리자"), make_account("관리자")
    wid = work_of(owner_admin)
    post(client, owner_admin, wid, "publish")
    post(client, other_admin, wid, "unpublish")               # 다른 관리자가 비공개
    assert post(client, owner_admin, wid, "publish").status_code == 403         # 자기 작품이어도 제작자 자격뿐
    assert post(client, owner_admin, wid, "return-to-owner").status_code == 403
    assert post(client, other_admin, wid, "return-to-owner").status_code == 200


def test_operator_cannot_force_publish_work_the_owner_made_private(client, make_account, work_of):
    owner, operator = make_account(), make_account("운영자")
    wid = work_of(owner)
    post(client, owner, wid, "publish")
    post(client, owner, wid, "unpublish")
    assert post(client, operator, wid, "publish").status_code == 403           # 저작권(제작자의 결정) 존중
    assert post(client, operator, wid, "return-to-owner").status_code == 409   # 이미 제작자에게 있음


# ---- 공개 조건: 확정된 버전 (B10) ---------------------------------------------------------

def test_work_without_confirmed_version_cannot_be_published(client, make_account):
    owner = make_account()
    wid = client.post("/api/works", headers=owner.headers, json={"제목": "미확정"}).json()["번호"]
    res = post(client, owner, wid, "publish")
    assert res.status_code == 409 and "확정된 버전" in res.json()["detail"]
    assert state(client, owner, wid) == (False, "제작자")


def test_confirmed_flag_is_reported_and_enables_publishing(client, make_account, confirm):
    owner = make_account()
    wid = client.post("/api/works", headers=owner.headers, json={"제목": "t"}).json()["번호"]
    assert client.get(f"/api/works/{wid}", headers=owner.headers).json()["확정버전_있음"] is False
    confirm(wid)
    assert client.get(f"/api/works/{wid}", headers=owner.headers).json()["확정버전_있음"] is True
    assert client.get("/api/works", headers=owner.headers).json()[0]["확정버전_있음"] is True
    assert post(client, owner, wid, "publish").status_code == 200


def test_permission_is_checked_before_the_confirmed_version_condition(client, make_account):
    owner, admin, stranger = make_account(), make_account("관리자"), make_account()
    wid = client.post("/api/works", headers=owner.headers, json={"제목": "미확정"}).json()["번호"]
    assert post(client, stranger, wid, "publish").status_code == 404   # 남은 존재조차 모른다
    assert post(client, admin, wid, "publish").status_code == 403      # 권한 없음이 먼저


def test_staff_cannot_publish_unconfirmed_work_either(client, make_account, confirm, test_dbname):
    # 관리자가 잠근 작품이라도 확정 버전이 없으면 공개할 수 없다 (조건은 누가 공개하든 같다)
    import psycopg

    owner, admin = make_account(), make_account("관리자")
    wid = client.post("/api/works", headers=owner.headers, json={"제목": "t"}).json()["번호"]
    confirm(wid)
    post(client, owner, wid, "publish")
    post(client, admin, wid, "unpublish")
    with psycopg.connect(f"dbname={test_dbname}", autocommit=True) as c:
        c.execute('DELETE FROM "버전" WHERE "작품_번호" = %s', (wid,))
    res = post(client, admin, wid, "publish")
    assert res.status_code == 409


def test_unpublish_and_return_do_not_need_a_confirmed_version(client, make_account, confirm, test_dbname):
    import psycopg

    owner, admin = make_account(), make_account("관리자")
    wid = client.post("/api/works", headers=owner.headers, json={"제목": "t"}).json()["번호"]
    confirm(wid)
    post(client, owner, wid, "publish")
    with psycopg.connect(f"dbname={test_dbname}", autocommit=True) as c:
        c.execute('DELETE FROM "버전" WHERE "작품_번호" = %s', (wid,))
    assert post(client, admin, wid, "unpublish").status_code == 200     # 문제 작품은 언제든 비공개할 수 있다
    assert post(client, admin, wid, "return-to-owner").status_code == 200
