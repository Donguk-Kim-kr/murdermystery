"""작품 콘텐츠 API(content.py): 어떤 항목이든 어떤 순서로든 만들 수 있고, 소유자만 접근한다."""
import pytest


def work(client, headers, **kw):
    res = client.post("/api/works", headers=headers, json={"제목": "저택의 비밀", **kw})
    assert res.status_code == 201, res.text
    return res.json()["번호"]


def url(w, key, item=None):
    return f"/api/works/{w}/content/{key}" + (f"/{item}" if item is not None else "")


def add(client, headers, w, key, **body):
    res = client.post(url(w, key), headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def character(client, headers, w, name="A"):
    res = client.post(f"/api/works/{w}/characters", headers=headers, json={"이름": name})
    assert res.status_code == 201, res.text
    return res.json()["순서"]


def test_schema_lists_every_resource_with_fields(client, headers):
    res = client.get("/api/content/schema", headers=headers)
    assert res.status_code == 200
    body = res.json()
    keys = {r["key"] for r in body["resources"]}
    assert {"places", "clues", "testimonies", "combos", "combo-parts", "incidents", "incident-details",
            "timelines", "endings", "epilogues", "relations", "votes", "materials", "phases",
            "phase-steps", "gimmick-uses"} <= keys
    places = next(r for r in body["resources"] if r["key"] == "places")
    names = {f["name"]: f for f in places["fields"]}
    assert names["이름"]["required"] is True and names["유형"]["required"] is False
    assert names["상위_장소_순서"]["ref"] == "places"
    assert client.get("/api/content/schema").status_code == 401


def test_items_can_be_created_in_any_order_with_per_work_numbering(client, headers):
    w, other = work(client, headers), work(client, headers, 제목="다른 작품")
    # 인물보다 단서·장소·사건부터 만들어도 된다
    clue = add(client, headers, w, "clues", 이름="찢어진 편지")
    place = add(client, headers, w, "places", 이름="서재")
    place2 = add(client, headers, w, "places", 이름="지하실", 상위_장소_순서=place["순서"])
    first_in_other = add(client, headers, other, "places", 이름="정원")
    assert (clue["순서"], place["순서"], place2["순서"]) == (1, 1, 2)
    assert first_in_other["순서"] == 1  # 작품별로 1부터
    assert place2["상위_장소_순서"] == 1


def test_required_fields_and_types_are_validated(client, headers):
    w = work(client, headers)
    for key, body in (
        ("places", {}),                                  # 이름 필수
        ("places", {"이름": "  "}),                      # 공백만
        ("places", {"이름": "서재", "유형": 3}),         # 글자가 아님
        ("testimonies", {"이름": "집사의 증언"}),         # 내용 필수
        ("phases", {"진행시간": -5}),
        ("phases", {"진행시간": "많이"}),
        ("endings", {"이름": "엔딩", "조건": [1], "내용": "x"}),  # JSON 객체여야 함
        ("endings", {"내용": "x"}),                      # 이름 필수
        ("clues", {"이름": "a", "없는칸": 1}),           # 알 수 없는 칸
        ("timelines", {"설명": "a", "시작시간": "어제"}),
    ):
        res = client.post(url(w, key), headers=headers, json=body)
        assert res.status_code == 422, (key, body, res.text)
    assert client.get(url(w, "places"), headers=headers).json() == []


def test_defaults_apply_when_a_field_is_omitted(client, headers):
    w = work(client, headers)
    assert add(client, headers, w, "phases")["진행시간"] == 30
    ending = add(client, headers, w, "endings", 이름="검거 엔딩", 내용="범인이 잡혔다")
    assert ending["조건"] == {}


def test_dates_and_json_round_trip(client, headers):
    w = work(client, headers)
    inc = add(client, headers, w, "incidents", 설명="살인")
    c = character(client, headers, w)
    detail = add(client, headers, w, "incident-details", 사건_순서=inc["순서"], 인물_순서=c, 상태="사망",
                 추정발생시간="2026-10-14T21:30:00", 추정종료시간="2026-10-14T22:10")
    assert detail["추정발생시간"].startswith("2026-10-14T21:30")
    vote = add(client, headers, w, "votes", 진행순서_순서=add(client, headers, w, "phases")["순서"],
               이름="최종 투표", 내용="범인은?", 규칙={"표": 1, "공개": False})
    assert vote["규칙"] == {"표": 1, "공개": False}


def test_references_must_point_to_this_work(client, headers):
    w, other = work(client, headers), work(client, headers, 제목="다른 작품")
    foreign_place = add(client, headers, other, "places", 이름="남의 장소")
    res = client.post(url(w, "clues"), headers=headers, json={"이름": "a", "장소_순서": foreign_place["순서"]})
    assert res.status_code == 422
    # 같은 번호가 이 작품에도 있으면 이 작품의 것을 가리키게 된다 (번호는 작품 안에서만 의미가 있다)
    mine = add(client, headers, w, "places", 이름="내 장소")
    ok = client.post(url(w, "clues"), headers=headers, json={"이름": "b", "장소_순서": mine["순서"]})
    assert ok.status_code == 201


def test_update_changes_only_given_fields_and_can_clear_optional_ones(client, headers):
    w = work(client, headers)
    p = add(client, headers, w, "places", 이름="서재", 유형="방", 특징="먼지가 많다")
    res = client.patch(url(w, "places", p["순서"]), headers=headers, json={"이름": "큰 서재", "특징": None})
    assert res.status_code == 200
    body = res.json()
    assert (body["이름"], body["유형"], body["특징"]) == ("큰 서재", "방", None)
    assert client.patch(url(w, "places", p["순서"]), headers=headers, json={"이름": None}).status_code == 422
    assert client.patch(url(w, "places", 99), headers=headers, json={"이름": "x"}).status_code == 404


def test_delete_is_blocked_while_other_items_use_it(client, headers):
    w = work(client, headers)
    place = add(client, headers, w, "places", 이름="서재")
    add(client, headers, w, "clues", 이름="편지", 장소_순서=place["순서"])
    res = client.delete(url(w, "places", place["순서"]), headers=headers)
    assert res.status_code == 409
    assert client.delete(url(w, "clues", 1), headers=headers).status_code == 204
    assert client.delete(url(w, "places", place["순서"]), headers=headers).status_code == 204
    assert client.delete(url(w, "places", place["순서"]), headers=headers).status_code == 404


def test_combo_part_needs_exactly_one_ingredient(client, headers):
    w = work(client, headers)
    combo = add(client, headers, w, "combos", 이름="완성된 편지")
    clue = add(client, headers, w, "clues", 이름="조각 1")
    testimony = add(client, headers, w, "testimonies", 이름="집사의 증언", 공개이름="집사", 내용="봤습니다")
    base = {"결과_조합_순서": combo["순서"]}
    assert client.post(url(w, "combo-parts"), headers=headers, json=base).status_code == 422
    assert client.post(url(w, "combo-parts"), headers=headers,
                       json={**base, "단서_순서": clue["순서"], "증언_순서": testimony["순서"]}).status_code == 422
    part = add(client, headers, w, "combo-parts", **base, 단서_순서=clue["순서"])
    assert part["번호"] and part["단서_순서"] == clue["순서"]
    # 재료로 쓰인 단서는 지울 수 없다
    assert client.delete(url(w, "clues", clue["순서"]), headers=headers).status_code == 409
    # 조합을 지우면 그 재료 줄도 함께 지워진다
    assert client.delete(url(w, "combos", combo["순서"]), headers=headers).status_code == 204
    assert client.get(url(w, "combo-parts"), headers=headers).json() == []


def test_relations_use_character_numbers_and_duplicates_are_allowed_to_differ(client, headers):
    w = work(client, headers)
    a, b = character(client, headers, w, "A"), character(client, headers, w, "B")
    rel = add(client, headers, w, "relations", 인물_순서=a, 대상_인물_순서=b, 관계="형제")
    assert rel["번호"] and rel["관계"] == "형제"
    assert client.post(url(w, "relations"), headers=headers,
                       json={"인물_순서": a, "대상_인물_순서": 99, "관계": "?"}).status_code == 422


def test_phase_numbers_are_assigned_in_creation_order_and_deletion_is_guarded(client, headers):
    w = work(client, headers)
    p1, p2 = add(client, headers, w, "phases", 진행시간=15), add(client, headers, w, "phases", 진행시간=40)
    assert (p1["순서"], p2["순서"]) == (1, 2)
    vote = add(client, headers, w, "votes", 진행순서_순서=2, 이름="v", 내용="c")
    assert client.delete(url(w, "phases", 2), headers=headers).status_code == 409   # 투표가 가리킴
    assert client.delete(url(w, "votes", vote["순서"]), headers=headers).status_code == 204
    assert client.delete(url(w, "phases", 2), headers=headers).status_code == 204
    assert add(client, headers, w, "phases")["순서"] == 2   # 결번은 다시 쓰인다 (현재 마지막 번호 + 1)


def test_only_the_owner_can_read_or_write(client, new_user):
    owner, other = new_user(), new_user()
    w = work(client, owner)
    add(client, owner, w, "places", 이름="서재")
    for method, path, body in (
        ("get", url(w, "places"), None), ("get", f"/api/works/{w}/content", None),
        ("post", url(w, "places"), {"이름": "x"}), ("patch", url(w, "places", 1), {"이름": "x"}),
        ("delete", url(w, "places", 1), None),
    ):
        res = getattr(client, method)(path, headers=other, **({"json": body} if body is not None else {}))
        assert res.status_code == 404, (method, path)
    assert client.get(url(w, "places"), headers=owner).json()[0]["이름"] == "서재"


def test_unknown_resource_is_404(client, headers):
    w = work(client, headers)
    assert client.get(url(w, "nothing"), headers=headers).status_code == 404


def test_bundle_returns_everything_and_library_names(client, headers):
    w = work(client, headers)
    character(client, headers, w, "탐정")
    add(client, headers, w, "places", 이름="서재")
    add(client, headers, w, "materials", 제목="프롤로그 이후", 내용="글")
    res = client.get(f"/api/works/{w}/content", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["places"][0]["이름"] == "서재"
    assert body["materials"][0]["제목"] == "프롤로그 이후"
    assert body["characters"][0]["이름"] == "탐정"
    assert body["library"] == {"phases": {}, "gimmicks": {}}


def test_writes_touch_the_modified_time(client, headers):
    w = work(client, headers)
    assert client.get(f"/api/works/{w}", headers=headers).json()["수정일시"] is None
    add(client, headers, w, "places", 이름="서재")
    assert client.get(f"/api/works/{w}", headers=headers).json()["수정일시"] is not None


def test_combo_is_made_with_its_ingredients_in_one_request(client, headers):
    w = work(client, headers)
    clue = add(client, headers, w, "clues", 이름="커터칼", 공개이름="A의 서랍")
    testimony = add(client, headers, w, "testimonies", 이름="A의 마약소문", 공개이름="지나가던 사람", 내용="들었습니다")
    assert (clue["공개이름"], testimony["공개이름"]) == ("A의 서랍", "지나가던 사람")
    inner = add(client, headers, w, "combos", 이름="안쪽", 재료=[{"종류": "단서", "순서": clue["순서"]}])
    # 같은 재료를 여러 번 넣어도 한 번만 참조된다. 순서는 넣은 순서 그대로이다
    combo = add(client, headers, w, "combos", 이름="완성", 공개이름="수상한 물건", 재료=[
        {"종류": "증언", "순서": testimony["순서"]}, {"종류": "단서", "순서": clue["순서"]},
        {"종류": "증언", "순서": testimony["순서"]}, {"종류": "조합", "순서": inner["순서"]},
    ])
    assert combo["재료"] == [
        {"종류": "증언", "순서": testimony["순서"]}, {"종류": "단서", "순서": clue["순서"]}, {"종류": "조합", "순서": inner["순서"]},
    ]
    assert client.get(url(w, "combos"), headers=headers).json()[1]["재료"] == combo["재료"]
    rows = client.get(url(w, "combo-parts"), headers=headers).json()                       # DB 에는 재료마다 한 줄로 나뉜다
    assert len([r for r in rows if r["결과_조합_순서"] == combo["순서"]]) == 3
    assert client.get(f"/api/works/{w}/content", headers=headers).json()["combos"][1]["재료"] == combo["재료"]
    # 재료만 바꾸어 고치면 통째로 바뀐다. 재료를 보내지 않으면 그대로이다
    res = client.patch(url(w, "combos", combo["순서"]), headers=headers, json={"재료": [{"종류": "단서", "순서": clue["순서"]}]})
    assert res.status_code == 200 and res.json()["재료"] == [{"종류": "단서", "순서": clue["순서"]}]
    res = client.patch(url(w, "combos", combo["순서"]), headers=headers, json={"내용": "바뀐 내용"})
    assert res.json()["재료"] == [{"종류": "단서", "순서": clue["순서"]}] and res.json()["내용"] == "바뀐 내용"
    res = client.patch(url(w, "combos", combo["순서"]), headers=headers, json={"재료": []})
    assert res.status_code == 200 and res.json()["재료"] == []


def test_combo_ingredients_are_validated(client, headers):
    w = work(client, headers)
    clue = add(client, headers, w, "clues", 이름="커터칼")
    a = add(client, headers, w, "combos", 이름="A")
    b = add(client, headers, w, "combos", 이름="B", 재료=[{"종류": "조합", "순서": a["순서"]}])
    patch = lambda order, parts: client.patch(url(w, "combos", order), headers=headers, json={"재료": parts})
    assert patch(a["순서"], [{"종류": "조합", "순서": a["순서"]}]).status_code == 422                    # 자기 자신
    assert patch(a["순서"], [{"종류": "조합", "순서": b["순서"]}]).status_code == 422                    # A→B→A 순환
    assert patch(a["순서"], [{"종류": "단서", "순서": 99}]).status_code == 422                           # 없는 단서
    for bad in ("단서", [1], [{"종류": "물건", "순서": 1}], [{"종류": "단서", "순서": "1"}], [{"종류": "단서", "순서": True}]):
        assert patch(a["순서"], bad).status_code == 422, bad
    assert client.get(url(w, "combos"), headers=headers).json()[0]["재료"] == []                       # 실패하면 바뀌지 않는다
    assert patch(a["순서"], [{"종류": "단서", "순서": clue["순서"]}]).status_code == 200
    res = client.post(url(w, "combos"), headers=headers, json={"이름": "C", "재료": [{"종류": "단서", "순서": 99}]})
    assert res.status_code == 422
    assert len(client.get(url(w, "combos"), headers=headers).json()) == 2                              # 만들다 실패한 조합은 남지 않는다


def test_combo_parts_are_hidden_from_the_screen_but_stay_in_the_schema(client, headers):
    resources = {r["key"]: r for r in client.get("/api/content/schema", headers=headers).json()["resources"]}
    assert resources["combo-parts"]["hidden"] is True and resources["combos"]["has_parts"] is True
    assert resources["combos"]["hidden"] is False


def test_confirm_warns_about_a_combo_without_ingredients(client, headers):
    w = work(client, headers)
    clue = add(client, headers, w, "clues", 이름="커터칼")
    add(client, headers, w, "combos", 이름="빈 조합")
    add(client, headers, w, "combos", 이름="찬 조합", 재료=[{"종류": "단서", "순서": clue["순서"]}])
    warnings = client.get(f"/api/works/{w}/confirm/check", headers=headers).json()["warnings"]
    assert "조합 '빈 조합'에 재료가 없습니다." in warnings and not any("찬 조합" in x for x in warnings)
