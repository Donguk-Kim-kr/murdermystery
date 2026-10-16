def create(client, headers, **kw):
    res = client.post("/api/works", headers=headers, json={"제목": "저택의 비밀", **kw})
    assert res.status_code == 201, res.text
    return res.json()


def test_create_starts_with_temporary_capacity_of_one(client, headers):
    work = create(client, headers, 시놉시스="폭풍우 치는 밤", 장르="추리")
    assert (work["최소인원"], work["최대인원"]) == (1, 1)
    assert work["상태"] == "개발" and work["수정일시"] is None
    assert work["공개여부"] is False and work["공개권한"] == "제작자"
    assert work["확정버전_있음"] is False
    assert work["예상시간"] == "3시간"


def test_list_shows_only_my_works_newest_first(client, new_user):
    a, b = new_user(), new_user()
    first = create(client, a, 제목="첫째")
    second = create(client, a, 제목="둘째")
    create(client, b, 제목="남의 작품")
    res = client.get("/api/works", headers=a)
    assert [w["번호"] for w in res.json()] == [second["번호"], first["번호"]]


def test_update_changes_fields_and_stamps_modified_time(client, headers):
    work = create(client, headers)
    res = client.patch(f"/api/works/{work['번호']}", headers=headers, json={"제목": "새 제목", "장르": "스릴러"})
    assert res.status_code == 200
    body = res.json()
    assert (body["제목"], body["장르"], body["시놉시스"]) == ("새 제목", "스릴러", work["시놉시스"])
    assert body["수정일시"] is not None


def test_update_cannot_blank_required_fields(client, headers):
    work = create(client, headers)
    for patch in ({"제목": None}, {"제목": ""}, {"시놉시스": None}):
        assert client.patch(f"/api/works/{work['번호']}", headers=headers, json=patch).status_code == 422


def test_min_players_cannot_exceed_current_capacity(client, headers):
    work = create(client, headers)
    res = client.patch(f"/api/works/{work['번호']}", headers=headers, json={"최소인원": 4})
    assert res.status_code == 409
    assert client.get(f"/api/works/{work['번호']}", headers=headers).json()["최소인원"] == 1


def test_capacity_is_not_user_editable(client, headers):
    work = create(client, headers)
    client.patch(f"/api/works/{work['번호']}", headers=headers, json={"최대인원": 9})
    assert client.get(f"/api/works/{work['번호']}", headers=headers).json()["최대인원"] == 1


def test_other_users_work_is_hidden(client, new_user):
    owner, other = new_user(), new_user()
    wid = create(client, owner)["번호"]
    assert client.get(f"/api/works/{wid}", headers=other).status_code == 404
    assert client.patch(f"/api/works/{wid}", headers=other, json={"제목": "탈취"}).status_code == 404
    assert client.get("/api/works/999999", headers=owner).status_code == 404
    assert client.get(f"/api/works/{wid}", headers=owner).json()["제목"] == "저택의 비밀"


def test_requires_login(client):
    assert client.get("/api/works").status_code == 401
    assert client.post("/api/works", json={"제목": "x"}).status_code == 401


def test_validation(client, headers):
    assert client.post("/api/works", headers=headers, json={"제목": "가" * 101}).status_code == 422


def test_title_can_be_left_for_later(client, headers):
    """제목을 비워도(또는 빼도) 만들 수 있고, 제목없음으로 시작한다. 제목 칸 자체는 비울 수 없는 칸 그대로다."""
    for body in ({}, {"제목": ""}, {"제목": "   "}):
        res = client.post("/api/works", headers=headers, json=body)
        assert res.status_code == 201, res.text
        assert res.json()["제목"] == "제목없음"
    assert client.post("/api/works", headers=headers, json={"제목": "  저택의 비밀  "}).json()["제목"] == "저택의 비밀"
    wid = client.post("/api/works", headers=headers, json={}).json()["번호"]
    assert client.patch(f"/api/works/{wid}", headers=headers, json={"제목": "새 제목"}).json()["제목"] == "새 제목"
    assert client.patch(f"/api/works/{wid}", headers=headers, json={"제목": ""}).status_code == 422     # 고칠 때는 비울 수 없다


def test_untitled_is_an_ordinary_editable_title(client, headers):
    """임시 이름 '제목없음'은 특별하지 않다: 같은 이름이 여러 개여도 되고, 직접 그렇게 지어도 되며, 언제든 고칠 수 있다."""
    a = client.post("/api/works", headers=headers, json={}).json()
    b = client.post("/api/works", headers=headers, json={}).json()
    c = client.post("/api/works", headers=headers, json={"제목": "제목없음"}).json()
    assert {a["제목"], b["제목"], c["제목"]} == {"제목없음"} and len({a["번호"], b["번호"], c["번호"]}) == 3
    assert client.patch(f"/api/works/{c['번호']}", headers=headers, json={"제목": "저택의 비밀"}).json()["제목"] == "저택의 비밀"


def test_patch_cannot_change_visibility(client, headers):
    wid = create(client, headers)["번호"]
    res = client.patch(f"/api/works/{wid}", headers=headers, json={"제목": "새 제목", "공개여부": True, "공개권한": "운영자"})
    assert res.status_code == 200
    body = client.get(f"/api/works/{wid}", headers=headers).json()
    assert (body["제목"], body["공개여부"], body["공개권한"]) == ("새 제목", False, "제작자")



def test_common_story_is_optional_and_editable(client, headers):
    work = create(client, headers)
    assert work["공통스토리"] in (None, "")
    with_story = create(client, headers, 제목="이야기가 있는 작품", 공통스토리="폭풍우 치는 밤, 저택에 여덟 명이 모였다.")
    assert with_story["공통스토리"].startswith("폭풍우")
    res = client.patch(f"/api/works/{work['번호']}", headers=headers, json={"공통스토리": "새 프롤로그"})
    assert res.status_code == 200 and res.json()["공통스토리"] == "새 프롤로그"
    res = client.patch(f"/api/works/{work['번호']}", headers=headers, json={"공통스토리": ""})
    assert res.status_code == 200 and res.json()["공통스토리"] == ""
    assert client.patch(f"/api/works/{work['번호']}", headers=headers, json={"공통스토리": None}).status_code == 422
    too_long = "가" * 20001
    assert client.patch(f"/api/works/{work['번호']}", headers=headers, json={"공통스토리": too_long}).status_code == 422


def test_delete_removes_the_work_with_its_content(client, headers):
    w = create(client, headers, 제목="지울 작품")["번호"]
    client.post(f"/api/works/{w}/characters", headers=headers, json={"이름": "A"})
    client.post(f"/api/works/{w}/content/places", headers=headers, json={"이름": "서재"})
    client.post(f"/api/works/{w}/content/phases", headers=headers, json={})
    assert client.delete(f"/api/works/{w}", headers=headers).status_code == 204
    assert client.get(f"/api/works/{w}", headers=headers).status_code == 404
    assert all(x["번호"] != w for x in client.get("/api/works", headers=headers).json())
    assert client.delete(f"/api/works/{w}", headers=headers).status_code == 404     # 이미 없다


def test_only_the_owner_can_delete(client, new_user):
    owner, other = new_user(), new_user()
    w = create(client, owner)["번호"]
    assert client.delete(f"/api/works/{w}", headers=other).status_code == 404
    assert client.delete(f"/api/works/{w}").status_code == 401
    assert client.get(f"/api/works/{w}", headers=owner).status_code == 200          # 그대로 남아 있다


def test_work_with_a_room_cannot_be_deleted(client, headers, confirm):
    w = create(client, headers)["번호"]
    client.post(f"/api/works/{w}/characters", headers=headers, json={"이름": "A"})
    confirm(w)
    assert client.post("/api/rooms", headers=headers, json={"작품_번호": w}).status_code == 201
    res = client.delete(f"/api/works/{w}", headers=headers)
    assert res.status_code == 409 and "방" in res.json()["detail"]
    assert client.get(f"/api/works/{w}", headers=headers).status_code == 200
