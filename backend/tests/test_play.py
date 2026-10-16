"""플레이공간 작품 목록(play.py): 공개 작품 + 내가 비공개 플레이할 수 있는 작품, 확정 버전이 있는 것만."""


def make_work(client, owner, confirm, title, confirmed=True, public=False):
    wid = client.post("/api/works", headers=owner.headers, json={"제목": title, "시놉시스": "비 오는 밤"}).json()["번호"]
    client.post(f"/api/works/{wid}/characters", headers=owner.headers, json={"이름": "A", "범인": True, "비밀": "내가 범인"})
    if confirmed:
        confirm(wid)
    if public:
        assert client.post(f"/api/works/{wid}/publish", headers=owner.headers).status_code == 200
    return wid


def titles(client, who):
    res = client.get("/api/play-works", headers=who.headers)
    assert res.status_code == 200, res.text
    return {w["제목"]: w for w in res.json()}


def test_requires_login(client):
    assert client.get("/api/play-works").status_code == 401


def test_public_confirmed_work_is_listed_for_everyone_without_secrets(client, make_account, confirm):
    owner, other = make_account(), make_account()
    make_work(client, owner, confirm, "공개 작품", public=True)
    got = titles(client, other)["공개 작품"]
    assert got["비공개플레이"] is False and got["제작자"] and got["최대인원"] == 1
    assert set(got) == {"번호", "제목", "시놉시스", "장르", "최소인원", "최대인원", "예상시간", "제작자", "비공개플레이"}


def test_private_work_only_for_owner_and_testers(client, make_account, confirm):
    owner, tester, stranger = make_account(), make_account(), make_account()
    make_work(client, owner, confirm, "비공개 작품")
    wid = next(iter(titles(client, owner).values()))["번호"]
    assert titles(client, owner)["비공개 작품"]["비공개플레이"] is True       # 제작자 본인
    assert "비공개 작품" not in titles(client, stranger)
    login = client.get("/api/auth/me", headers=tester.headers).json()["아이디"]
    assert client.post(f"/api/works/{wid}/testers", headers=owner.headers, json={"아이디": login}).status_code == 201
    assert titles(client, tester)["비공개 작품"]["비공개플레이"] is True       # 테스터로 지정받은 사람
    assert "비공개 작품" not in titles(client, stranger)


def test_unconfirmed_work_is_not_listed(client, make_account, confirm):
    owner = make_account()
    make_work(client, owner, confirm, "미확정 작품", confirmed=False)
    assert "미확정 작품" not in titles(client, owner)
