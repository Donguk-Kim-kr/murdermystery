"""작품 테스터 권한 (DB_RULES B36)."""
import psycopg
import pytest

from app.testers import can_private_play


@pytest.fixture
def work_of(client, confirm):
    def make(owner):
        wid = client.post("/api/works", headers=owner.headers, json={"제목": "저택의 비밀"}).json()["번호"]
        confirm(wid)  # 공개하려면 확정 버전이 필요하다
        return wid
    return make


def add(client, who, wid, target):
    return client.post(f"/api/works/{wid}/testers", headers=who.headers, json={"아이디": target.login_id})


def private_play_ids(client, who):
    return [w["번호"] for w in client.get("/api/private-play-works", headers=who.headers).json()]


def pub(client, who, wid, action):
    return client.post(f"/api/works/{wid}/{action}", headers=who.headers)


def test_owner_grants_lists_and_revokes(client, make_account, work_of):
    owner, tester = make_account(), make_account()
    wid = work_of(owner)
    res = add(client, owner, wid, tester)
    assert res.status_code == 201 and res.json()["계정_번호"] == tester.number
    listed = client.get(f"/api/works/{wid}/testers", headers=owner.headers).json()
    assert [t["아이디"] for t in listed] == [tester.login_id]
    assert client.delete(f"/api/works/{wid}/testers/{tester.number}", headers=owner.headers).status_code == 204
    assert client.get(f"/api/works/{wid}/testers", headers=owner.headers).json() == []
    assert client.delete(f"/api/works/{wid}/testers/{tester.number}", headers=owner.headers).status_code == 404


def test_cannot_grant_twice_to_self_or_to_unknown_or_suspended(client, make_account, work_of, test_dbname):
    owner, tester, suspended = make_account(), make_account(), make_account()
    wid = work_of(owner)
    assert add(client, owner, wid, tester).status_code == 201
    assert add(client, owner, wid, tester).status_code == 409
    assert add(client, owner, wid, owner).status_code == 409
    with psycopg.connect(f"dbname={test_dbname}", autocommit=True) as c:
        c.execute('UPDATE "계정" SET "상태" = %s WHERE "번호" = %s', ("정지", suspended.number))
    assert add(client, owner, wid, suspended).status_code == 409
    res = client.post(f"/api/works/{wid}/testers", headers=owner.headers, json={"아이디": "no-such-user"})
    assert res.status_code == 404


def test_owner_can_only_grant_on_own_work(client, make_account, work_of):
    owner, other, tester = make_account(), make_account(), make_account()
    wid = work_of(owner)
    assert add(client, other, wid, tester).status_code == 404
    assert client.get(f"/api/works/{wid}/testers", headers=other.headers).status_code == 404
    add(client, owner, wid, tester)
    assert client.delete(f"/api/works/{wid}/testers/{tester.number}", headers=other.headers).status_code == 404


@pytest.mark.parametrize("role", ["관리자", "운영자"])
def test_admin_and_operator_can_grant_on_any_work(client, make_account, work_of, role):
    owner, staff, tester = make_account(), make_account(role), make_account()
    wid = work_of(owner)
    assert add(client, staff, wid, tester).status_code == 201
    assert client.get(f"/api/works/{wid}/testers", headers=staff.headers).status_code == 200
    assert client.delete(f"/api/works/{wid}/testers/{tester.number}", headers=staff.headers).status_code == 204


def test_tester_cannot_manage_testers(client, make_account, work_of):
    owner, tester, third = make_account(), make_account(), make_account()
    wid = work_of(owner)
    add(client, owner, wid, tester)
    assert add(client, tester, wid, third).status_code == 404  # 테스터는 작품 존재 자체를 관리할 권한이 없다


def test_tester_can_test_before_first_publish(client, make_account, work_of):
    owner, tester, outsider = make_account(), make_account(), make_account()
    wid = work_of(owner)
    add(client, owner, wid, tester)
    assert wid in private_play_ids(client, tester)
    assert wid in private_play_ids(client, owner)        # 제작자 본인도 비공개 플레이할 수 있다
    assert wid not in private_play_ids(client, outsider)


def test_testable_summary_has_no_secrets(client, make_account, work_of):
    owner, tester = make_account(), make_account()
    wid = work_of(owner)
    client.post(f"/api/works/{wid}/characters", headers=owner.headers, json={"이름": "A", "비밀": "범인은 나다", "범인": True})
    add(client, owner, wid, tester)
    item = client.get("/api/private-play-works", headers=tester.headers).json()[0]
    assert set(item) == {"번호", "제목", "시놉시스", "장르", "최소인원", "최대인원", "예상시간"}


def test_testing_is_closed_while_public_and_reopens_when_owner_unpublishes(client, make_account, work_of):
    owner, tester = make_account(), make_account()
    wid = work_of(owner)
    add(client, owner, wid, tester)
    pub(client, owner, wid, "publish")
    assert wid not in private_play_ids(client, tester)   # 공개 중에는 테스터 권한이 쓰이지 않는다
    pub(client, owner, wid, "unpublish")
    assert wid in private_play_ids(client, tester)       # 제작자가 비공개한 경우


@pytest.mark.parametrize("role", ["관리자", "운영자"])
def test_testing_is_closed_when_staff_unpublished_until_returned_to_owner(client, make_account, work_of, role):
    owner, tester, staff = make_account(), make_account(), make_account(role)
    wid = work_of(owner)
    add(client, owner, wid, tester)
    pub(client, owner, wid, "publish")
    pub(client, staff, wid, "unpublish")
    assert wid not in private_play_ids(client, tester)
    assert wid not in private_play_ids(client, owner)
    pub(client, staff, wid, "return-to-owner")       # "수정해서 다시 공개하세요"
    assert wid in private_play_ids(client, tester)


def test_can_private_play_function(client, make_account, work_of, test_dbname):
    owner, tester, outsider = make_account(), make_account(), make_account()
    wid = work_of(owner)
    add(client, owner, wid, tester)
    with psycopg.connect(f"dbname={test_dbname}", autocommit=True) as c:
        assert can_private_play(c, tester.number, wid)
        assert can_private_play(c, owner.number, wid)
        assert not can_private_play(c, outsider.number, wid)
        assert not can_private_play(c, tester.number, 999999)


def test_grants_disappear_with_the_work_and_do_not_block_account_rules(client, make_account, work_of, test_dbname):
    owner, tester = make_account(), make_account()
    wid = work_of(owner)
    add(client, owner, wid, tester)
    with psycopg.connect(f"dbname={test_dbname}", autocommit=True) as c:
        c.execute('DELETE FROM "작품" WHERE "번호" = %s', (wid,))
        assert c.execute('SELECT count(*) FROM "테스터" WHERE "작품_번호" = %s', (wid,)).fetchone()[0] == 0
