"""작품에 붙는 이미지·영상: 올리기, 서명된 주소, 확정 스냅샷, 게임 화면 (app/media.py, 사용자 결정 2026-10-20)."""
import time

import pytest

from app import media
from app.config import get_settings
from app.default_phases import CHARACTER_SELECT, INVESTIGATE, PROLOGUE

from test_cards import answer, block, db, make_scripted_game, players_of, state, tab  # noqa: F401  (픽스처 포함)

PNG = b"\x89PNG\r\n\x1a\n" + b"png-body" * 8
JPG = b"\xff\xd8\xff\xe0" + b"jpg-body" * 8
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"webp-body" * 4
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"mp4-body" * 16
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heic" + b"x" * 32


@pytest.fixture(autouse=True)
def media_folder(tmp_path, monkeypatch):
    """시험마다 빈 저장 폴더를 쓴다."""
    monkeypatch.setenv("MM_MEDIA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


@pytest.fixture
def work(client, make_account):
    """인물 둘과 단서 둘이 있는 작품과 그 주인."""
    owner = make_account()
    wid = client.post("/api/works", headers=owner.headers, json={"제목": "미디어 시험"}).json()["번호"]
    for name in ("가", "나"):
        assert client.post(f"/api/works/{wid}/characters", headers=owner.headers, json={"이름": name}).status_code == 201
    for name in ("편지", "안경"):
        assert client.post(f"/api/works/{wid}/content/clues", headers=owner.headers, json={"이름": name}).status_code == 201
    return owner, wid


def put(client, who, wid, body, mime, **params):
    return client.put(f"/api/works/{wid}/media", headers={**who.headers, "Content-Type": mime}, params=params, content=body)


def test_upload_attaches_an_image_to_a_clue_and_serves_it_through_a_signed_address(client, work):
    owner, wid = work
    res = put(client, owner, wid, PNG, "image/png", 대상="단서", 번호=1)
    assert res.status_code == 201, res.text
    assert res.json()["대상"] == "단서" and res.json()["번호"] == 1 and res.json()["유형"] == "이미지"
    listed = client.get(f"/api/works/{wid}/media", headers=owner.headers).json()
    assert [(m["대상"], m["번호"], m["유형"]) for m in listed] == [("단서", 1, "이미지")]
    got = client.get(listed[0]["주소"])                     # 주소에 서명이 들어 있어 로그인 정보 없이도 받는다
    assert got.status_code == 200 and got.content == PNG and got.headers["content-type"] == "image/png"
    assert got.headers["cache-control"].startswith("private")


def test_each_allowed_format_is_accepted_and_stored_by_content_hash(client, work, media_folder):
    owner, wid = work
    assert put(client, owner, wid, JPG, "image/jpeg", 대상="인물", 번호=1).status_code == 201
    assert put(client, owner, wid, WEBP, "image/webp", 대상="인물", 번호=2).status_code == 201
    assert put(client, owner, wid, MP4, "video/mp4", 대상="공통스토리").status_code == 201
    names = sorted(p.name for p in media_folder.iterdir() if not p.name.startswith("."))
    assert len(names) == 3 and all(media.KEY_RE.match(n) for n in names)
    assert {n.rsplit(".", 1)[1] for n in names} == {"jpg", "webp", "mp4"}


def test_same_content_is_stored_once(client, work, media_folder):
    owner, wid = work
    put(client, owner, wid, PNG, "image/png", 대상="단서", 번호=1)
    put(client, owner, wid, PNG, "image/png", 대상="단서", 번호=2)
    assert len([p for p in media_folder.iterdir() if p.suffix == ".png"]) == 1


def test_wrong_content_type_target_or_size_is_refused(client, work, monkeypatch):
    owner, wid = work
    assert put(client, owner, wid, JPG, "image/png", 대상="단서", 번호=1).status_code == 415            # 말한 형식과 내용이 다르다
    assert put(client, owner, wid, b"GIF89a....", "image/gif", 대상="단서", 번호=1).status_code == 415   # 받지 않는 형식
    assert put(client, owner, wid, b"MZ\x90\x00 not an image", "image/png", 대상="단서", 번호=1).status_code == 415
    assert put(client, owner, wid, HEIC, "video/mp4", 대상="공통스토리").status_code == 415                # mp4 처럼 보여도 이미지 형식
    assert put(client, owner, wid, MP4, "video/mp4", 대상="단서", 번호=1).status_code == 422               # 단서에는 이미지만
    assert put(client, owner, wid, PNG, "image/png", 대상="공통스토리").status_code == 422                # 공통 스토리에는 영상만
    assert put(client, owner, wid, b"", "image/png", 대상="단서", 번호=1).status_code == 422
    assert put(client, owner, wid, PNG, "image/png", 대상="단서", 번호=99).status_code == 404             # 없는 단서
    assert put(client, owner, wid, PNG, "image/png", 대상="장소", 번호=1).status_code == 422
    monkeypatch.setenv("MM_MEDIA_MAX_IMAGE_BYTES", "40")
    get_settings.cache_clear()
    assert put(client, owner, wid, PNG, "image/png", 대상="단서", 번호=1).status_code == 413
    assert client.get(f"/api/works/{wid}/media", headers=owner.headers).json() == []                     # 실패한 것은 남지 않는다


def test_failed_upload_leaves_no_partial_file(client, work, media_folder, monkeypatch):
    owner, wid = work
    monkeypatch.setenv("MM_MEDIA_MAX_IMAGE_BYTES", "40")
    get_settings.cache_clear()
    put(client, owner, wid, PNG, "image/png", 대상="단서", 번호=1)
    assert [p.name for p in media_folder.iterdir() if p.suffix in (".tmp", ".png")] == []


def test_only_the_owner_can_attach_or_list(client, work, make_account):
    owner, wid = work
    stranger = make_account()
    assert put(client, stranger, wid, PNG, "image/png", 대상="단서", 번호=1).status_code == 404
    assert client.get(f"/api/works/{wid}/media", headers=stranger.headers).status_code == 404
    assert client.put(f"/api/works/{wid}/media", params={"대상": "단서", "번호": 1}, content=PNG,
                      headers={"Content-Type": "image/png"}).status_code == 401


def test_uploading_again_replaces_and_delete_removes(client, work):
    owner, wid = work
    put(client, owner, wid, PNG, "image/png", 대상="단서", 번호=1)
    second = put(client, owner, wid, JPG, "image/jpeg", 대상="단서", 번호=1).json()
    listed = client.get(f"/api/works/{wid}/media", headers=owner.headers).json()
    assert len(listed) == 1 and listed[0]["순서"] == second["순서"]                  # 한 대상에 하나만 붙는다
    assert client.delete(f"/api/works/{wid}/media/{second['순서']}", headers=owner.headers).status_code == 204
    assert client.get(f"/api/works/{wid}/media", headers=owner.headers).json() == []
    assert client.delete(f"/api/works/{wid}/media/{second['순서']}", headers=owner.headers).status_code == 404


def test_deleting_a_clue_or_character_removes_its_media(client, work, db):
    owner, wid = work
    put(client, owner, wid, PNG, "image/png", 대상="단서", 번호=1)
    put(client, owner, wid, JPG, "image/jpeg", 대상="인물", 번호=1)
    assert client.delete(f"/api/works/{wid}/content/clues/1", headers=owner.headers).status_code == 204
    assert client.delete(f"/api/works/{wid}/characters/1", headers=owner.headers).status_code == 204
    assert client.get(f"/api/works/{wid}/media", headers=owner.headers).json() == []


def test_signed_address_rejects_tampering_and_expiry(client, work):
    owner, wid = work
    url = put(client, owner, wid, PNG, "image/png", 대상="단서", 번호=1).json()["주소"]
    assert client.get(url).status_code == 200
    assert client.get(url.replace("&s=", "&s=0")).status_code == 403                     # 서명이 다르다
    assert client.get(url.replace("a=", "a=9")).status_code == 403                       # 다른 계정의 것으로 바꿀 수 없다
    key = url.split("?")[0].rsplit("/", 1)[1]
    old = media.signed_url(key, 1, now=time.time() - 10 * 3600)
    assert client.get(old).status_code == 403                                            # 만료
    assert client.get("/api/media/..%2F..%2Fetc%2Fpasswd?a=1&e=99999999999&s=x").status_code in (403, 404)
    assert client.get(f"/api/media/{'0' * 64}.png?a=1&e={int(time.time()) + 100}&s={'0' * 32}").status_code == 403


def test_video_supports_range_requests(client, work):
    owner, wid = work
    url = put(client, owner, wid, MP4, "video/mp4", 대상="공통스토리").json()["주소"]
    part = client.get(url, headers={"Range": "bytes=0-9"})
    assert part.status_code == 206 and part.content == MP4[:10]


def test_confirm_keeps_media_keys_and_refuses_when_a_file_is_missing(client, work, db, media_folder):
    owner, wid = work
    assert client.post(f"/api/works/{wid}/phases/insert", headers=owner.headers, json={"position": 1}).status_code == 201
    put(client, owner, wid, PNG, "image/png", 대상="단서", 번호=1)
    put(client, owner, wid, MP4, "video/mp4", 대상="공통스토리")
    assert client.post(f"/api/works/{wid}/confirm", headers=owner.headers, json={}).status_code == 201
    snapshot = db.execute('SELECT "시나리오" FROM "버전" WHERE "작품_번호" = %s', (wid,)).fetchone()[0]
    assert [(m["단서_순서"], m["공통스토리"], m["유형"]) for m in snapshot["미디어"]] == [(1, False, "이미지"), (None, True, "영상")]
    assert all(media.KEY_RE.match(m["경로"]) for m in snapshot["미디어"])
    for f in media_folder.glob("*.png"):
        f.unlink()
    check = client.get(f"/api/works/{wid}/confirm/check", headers=owner.headers).json()
    assert any("단서 1" in e and "저장소에 없습니다" in e for e in check["errors"])
    assert client.post(f"/api/works/{wid}/confirm", headers=owner.headers, json={}).status_code == 422


# 단서 순서: 1 찢어진 편지(서재) 2 깨진 안경(서재) 3 독이 든 컵(주방) — test_investigation 과 같은 구성이 아니라 이 시험에서만 쓴다
def build_with_media(client, host, wid):
    url = f"/api/works/{wid}/content"
    study = client.post(f"{url}/places", headers=host.headers, json={"이름": "서재"}).json()["순서"]
    client.post(f"{url}/clues", headers=host.headers, json={"이름": "찢어진 편지", "내용": "편지 내용", "장소_순서": study})
    client.post(f"{url}/clues", headers=host.headers, json={"이름": "깨진 안경", "내용": "안경 내용", "장소_순서": study})
    assert put(client, host, wid, PNG, "image/png", 대상="단서", 번호=1).status_code == 201
    assert put(client, host, wid, JPG, "image/jpeg", 대상="인물", 번호=1).status_code == 201
    assert put(client, host, wid, MP4, "video/mp4", 대상="공통스토리").status_code == 201


@pytest.fixture
def game(client, make_scripted_game):
    host, others, room, wid = make_scripted_game(
        [("공통 스토리", PROLOGUE, {}), ("캐릭터 선택", CHARACTER_SELECT, {"설명보이기": True}), ("조사", INVESTIGATE, {"횟수": 3})],
        setup=build_with_media,
    )
    return players_of(host, others), room


def advance(client, host):
    assert client.post("/api/game/me/advance", headers=host.headers).status_code == 200


def test_common_story_tab_carries_a_signed_video_address_for_everyone(client, game):
    people, _ = game
    for who in people:
        story = tab(state(client, who).json(), "공통 스토리")
        assert story["영상"].startswith("/api/media/") and "&s=" in story["영상"]
        got = client.get(story["영상"])
        assert got.status_code == 200 and got.content == MP4
        assert "경로" not in story and ".mp4" not in story["내용"]                 # 키(경로)는 화면에 내보내지 않는다


def test_character_cards_show_the_portrait_only_where_one_was_attached(client, game):
    people, _ = game
    host = people[0]
    advance(client, host)                                  # 캐릭터 선택은 둘째 페이즈
    view = state(client, host).json()
    items = {i["값"]: i for i in block(view, "캐릭터 선택")["항목"]}
    assert items[1]["이미지"].startswith("/api/media/") and "이미지" not in items[2]
    assert client.get(items[1]["이미지"]).content == JPG
    assert next(c for c in view["인물"] if c["순서"] == 1)["이미지"] == items[1]["이미지"]
    assert next(c for c in view["인물"] if c["순서"] == 2)["이미지"] is None


def test_a_clue_image_reaches_only_the_player_who_holds_the_clue(client, game):
    people, _ = game
    host, second = people[0], people[1]
    advance(client, host)
    for slot, who in enumerate(people, 1):
        assert answer(client, who, block(state(client, who).json(), "캐릭터 선택")["질문ID"], slot).status_code == 200
    advance(client, host)
    qid = block(state(client, host).json(), "조사 대상")["질문ID"]
    first_clue = next(i["값"] for i in block(state(client, host).json(), "조사 대상")["항목"] if i["이름"] == "찢어진 편지")
    assert answer(client, host, qid, first_clue).status_code == 200
    mine = tab(state(client, host).json(), "내 단서")["항목"]
    assert [c["이름"] for c in mine] == ["찢어진 편지"] and mine[0]["이미지"].startswith("/api/media/")
    assert client.get(mine[0]["이미지"]).content == PNG
    other = tab(state(client, second).json(), "내 단서")["항목"]
    assert other == []                                                                   # 가지지 못한 사람에게는 카드도 이미지도 나가지 않는다
    assert "이미지" not in str(block(state(client, second).json(), "조사 대상"))      # 조사 목록에는 이미지가 없다(획득한 사람의 카드 안에서만 보인다)


def test_cover_is_an_image_for_the_work_one_per_work_replaced_and_deleted(client, work):
    owner, wid = work
    assert put(client, owner, wid, MP4, "video/mp4", 대상="표지").status_code == 422          # 표지는 이미지만
    first = put(client, owner, wid, PNG, "image/png", 대상="표지")
    assert first.status_code == 201, first.text
    assert first.json()["대상"] == "표지" and first.json()["번호"] is None and first.json()["유형"] == "이미지"
    assert put(client, owner, wid, JPG, "image/jpeg", 대상="표지").status_code == 201          # 다시 올리면 바뀐다
    listed = client.get(f"/api/works/{wid}/media", headers=owner.headers).json()
    assert [(m["대상"], m["번호"]) for m in listed] == [("표지", None)]
    assert client.get(listed[0]["주소"]).content == JPG
    assert client.delete(f"/api/works/{wid}/media/{listed[0]['순서']}", headers=owner.headers).status_code == 204
    assert client.get(f"/api/works/{wid}/media", headers=owner.headers).json() == []


def test_cover_only_the_owner_can_attach(client, work, make_account):
    owner, wid = work
    assert put(client, make_account(), wid, PNG, "image/png", 대상="표지").status_code in (403, 404)
    assert client.get(f"/api/works/{wid}/media", headers=owner.headers).json() == []


def test_play_list_carries_a_cover_address_for_everyone_who_sees_the_work(client, make_account, confirm):
    from test_play import make_work, titles

    owner, other = make_account(), make_account()
    with_cover = make_work(client, owner, confirm, "표지 있는 작품", public=True)
    make_work(client, owner, confirm, "표지 없는 작품", public=True)
    assert put(client, owner, with_cover, PNG, "image/png", 대상="표지").status_code == 201
    seen = titles(client, other)
    assert seen["표지 없는 작품"]["표지"] is None
    got = client.get(seen["표지 있는 작품"]["표지"])
    assert got.status_code == 200 and got.content == PNG
    assert f"a={other.number}" in seen["표지 있는 작품"]["표지"]            # 보는 사람 자신의 주소
    for f in media.media_dir().glob("*.png"):                              # 저장소에서 파일이 사라지면 표지 없음으로 보인다
        f.unlink()
    assert titles(client, other)["표지 있는 작품"]["표지"] is None


def test_cover_is_not_part_of_the_confirmed_scenario_and_never_blocks_confirm(client, work, db, media_folder):
    owner, wid = work
    assert client.post(f"/api/works/{wid}/phases/insert", headers=owner.headers, json={"position": 1}).status_code == 201
    assert put(client, owner, wid, PNG, "image/png", 대상="표지").status_code == 201
    assert client.post(f"/api/works/{wid}/confirm", headers=owner.headers, json={}).status_code == 201
    snapshot = db.execute('SELECT "시나리오" FROM "버전" WHERE "작품_번호" = %s', (wid,)).fetchone()[0]
    assert snapshot["미디어"] == []
    for f in media_folder.glob("*.png"):
        f.unlink()
    assert client.get(f"/api/works/{wid}/confirm/check", headers=owner.headers).json()["errors"] == []


def test_demo_media_folder_is_attached_by_file_name(client, work, tmp_path):
    """시연용 폴더: 파일 이름으로 인물·단서·공통 스토리를 정한다. 다른 파일과 이름이 없는 파일은 건너뛴다."""
    import unicodedata

    from app.demo_work import attach_demo_media

    owner, wid = work
    folder = tmp_path / "demo"
    folder.mkdir()
    (folder / unicodedata.normalize("NFD", "인물-가.png")).write_bytes(PNG)               # 맥에서 만든 분해형 이름도 맞는다
    (folder / "단서-편지.jpg").write_bytes(JPG)
    (folder / "공통스토리.mp4").write_bytes(MP4)
    (folder / "표지.webp").write_bytes(WEBP)
    (folder / "단서-없는 단서.png").write_bytes(PNG)
    (folder / "README.md").write_text("설명")
    (folder / ".DS_Store").write_bytes(b"x")
    lines = attach_demo_media(client, owner.headers, wid, folder, {"가": 1, "나": 2}, {"편지": 1, "안경": 2})
    assert sorted(l.split(":")[0] for l in lines) == ["건너뜀", "붙임", "붙임", "붙임", "붙임"]
    assert any("없는 단서" in l for l in lines if l.startswith("건너뜀"))
    listed = client.get(f"/api/works/{wid}/media", headers=owner.headers).json()
    assert sorted((m["대상"], m["번호"]) for m in listed if m["번호"] is not None) == [("단서", 1), ("인물", 1)]
    assert any(m["대상"] == "공통스토리" and m["유형"] == "영상" for m in listed)
    assert any(m["대상"] == "표지" and m["유형"] == "이미지" for m in listed)
    assert attach_demo_media(client, owner.headers, wid, tmp_path / "없는 폴더", {}, {}) == []
