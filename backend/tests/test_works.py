def create(client, headers, **kw):
    res = client.post("/api/works", headers=headers, json={"제목": "저택의 비밀", **kw})
    assert res.status_code == 201, res.text
    return res.json()


def test_create_starts_with_temporary_capacity_of_one(client, headers):
    work = create(client, headers, 시놉시스="폭풍우 치는 밤", 장르="추리")
    assert (work["최소인원"], work["최대인원"]) == (1, 1)
    assert work["상태"] == "개발" and work["수정일시"] is None
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
    assert client.post("/api/works", headers=headers, json={"제목": ""}).status_code == 422
    assert client.post("/api/works", headers=headers, json={}).status_code == 422
