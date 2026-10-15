"""재사용 라이브러리 API(library.py): 버전 올리기·삭제·계열 이름 변경·공통 항목 권한."""
import pytest

PHASE = {"설명": "조사 단계", "규칙": {"시간": 600}}


def url(kind, item=None):
    return f"/api/library/{kind}" + (f"/{item}" if item is not None else "")


def create(client, headers, kind="phases", **body):
    body = {"이름": "나만의 조사", **PHASE, **body} if kind == "phases" else {"이름": "독 발견", **body}
    res = client.post(url(kind), headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def names(client, headers, kind="phases", **params):
    return [(r["이름"], r["버전"]) for r in client.get(url(kind), headers=headers, params=params).json()]


def test_requires_login_and_known_kind(client, headers):
    assert client.get(url("phases")).status_code == 401
    assert client.get(url("nope"), headers=headers).status_code == 404


def test_same_name_creates_next_version(client, make_account):
    a = make_account().headers
    v1 = create(client, a, 이름="회의", 변경내역=None)
    v2 = create(client, a, 이름="회의", 변경내역="시간 연장", 규칙={"시간": 900})
    assert (v1["버전"], v2["버전"]) == (1, 2) and v2["변경내역"] == "시간 연장"
    assert v1["공통"] is False and v1["규칙"] == {"시간": 600}
    assert [r["버전"] for r in client.get(url("phases"), headers=a).json() if r["이름"] == "회의"] == [2, 1]


def test_other_accounts_cannot_see_or_touch_my_items(client, make_account):
    a, b = make_account().headers, make_account().headers
    item = create(client, a, 이름="비밀 단계")
    assert all(r["이름"] != "비밀 단계" for r in client.get(url("phases"), headers=b).json())
    assert client.patch(url("phases", item["번호"]), headers=b, json={"이름": "x"}).status_code == 404
    assert client.delete(url("phases", item["번호"]), headers=b).status_code == 404
    # 같은 이름을 만들어도 서로의 버전에 영향이 없다
    other = create(client, b, 이름="비밀 단계")
    assert other["버전"] == 1


def test_validation(client, headers):
    for kind, body in (
        ("phases", {"설명": "없음"}),                          # 이름 필수
        ("phases", {"이름": "x", "규칙": []}),                  # JSON 객체여야 함
        ("phases", {"이름": "x", "설명": "d", "몰래": 1}),      # 알 수 없는 항목
        ("gimmicks", {"이름": "x", "조건": "문자열"}),
        ("phases", {"이름": " ", "설명": "d"}),
    ):
        assert client.post(url(kind), headers=headers, json=body).status_code == 422, body
    # 기믹은 설명이 없어도 된다
    ok = client.post(url("gimmicks"), headers=headers, json={"이름": "독 발견", "조건": {}, "결과": {}})
    assert ok.status_code == 201 and ok.json()["설명"] is None


def test_delete_version_then_new_version_does_not_reuse_number(client, headers):
    create(client, headers, 이름="토론")
    v2 = create(client, headers, 이름="토론")
    assert client.delete(url("phases", v2["번호"]), headers=headers).status_code == 200
    assert ("토론", 2) not in names(client, headers) and ("토론", 1) in names(client, headers)
    assert ("토론", 2) in names(client, headers, include_deleted=True)
    assert create(client, headers, 이름="토론")["버전"] == 3
    assert client.delete(url("phases", v2["번호"]), headers=headers).status_code == 409  # 이미 삭제됨


def test_delete_whole_lineage(client, headers):
    create(client, headers, 이름="나만의 밀담")
    last = create(client, headers, 이름="나만의 밀담")
    res = client.delete(url("phases", last["번호"]) + "?scope=lineage", headers=headers)
    assert res.json() == {"삭제됨": 2}
    assert all(n != "나만의 밀담" for n, _ in names(client, headers))


def test_rename_lineage_changes_every_version(client, headers):
    create(client, headers, 이름="옛 이름")
    v2 = create(client, headers, 이름="옛 이름")
    res = client.patch(url("phases", v2["번호"]), headers=headers, json={"이름": "새 이름"})
    assert res.status_code == 200 and res.json()["이름"] == "새 이름"
    assert sorted(names(client, headers)) .count(("새 이름", 1)) == 1 and ("새 이름", 2) in names(client, headers)
    assert all(n != "옛 이름" for n, _ in names(client, headers, include_deleted=True))
    # 이름이 바뀐 뒤 새 버전은 새 이름의 다음 버전이 된다
    assert create(client, headers, 이름="새 이름")["버전"] == 3


def test_rename_collision_and_blank_are_rejected(client, headers):
    create(client, headers, 이름="가")
    b = create(client, headers, 이름="나")
    assert client.patch(url("phases", b["번호"]), headers=headers, json={"이름": "가"}).status_code == 409
    assert client.patch(url("phases", b["번호"]), headers=headers, json={"이름": " "}).status_code == 422
    assert client.patch(url("phases", b["번호"]), headers=headers, json={"규칙": {}}).status_code == 422  # 내용은 수정 불가
    assert client.patch(url("phases", b["번호"]), headers=headers, json={"이름": "나"}).status_code == 200


def test_share_flag_toggles(client, headers):
    item = create(client, headers, 이름="공유 후보")
    assert item["공개여부"] is False
    res = client.patch(url("phases", item["번호"]), headers=headers, json={"공개여부": True})
    assert res.json()["공개여부"] is True
    assert client.patch(url("phases", item["번호"]), headers=headers, json={"공개여부": "예"}).status_code == 422


def test_common_items_are_visible_to_all_but_changeable_only_by_operator(client, make_account):
    user, operator = make_account(), make_account("운영자")
    seeded = [r for r in client.get(url("phases"), headers=user.headers).json() if r["공통"]]
    assert len(seeded) >= 11  # 마이그레이션 0015 가 넣은 기본 진행단계
    target = seeded[0]
    assert client.delete(url("phases", target["번호"]), headers=user.headers).status_code == 403
    assert client.patch(url("phases", target["번호"]), headers=user.headers, json={"이름": "x"}).status_code == 403
    assert client.post(url("phases"), headers=user.headers, json={"이름": "x", "설명": "d", "공통": True}).status_code == 403
    made = client.post(url("phases"), headers=operator.headers,
                       json={"이름": "운영자 단계", "설명": "d", "공통": True})
    assert made.status_code == 201 and made.json()["공통"] is True and made.json()["계정_번호"] is None
    assert any(r["이름"] == "운영자 단계" for r in client.get(url("phases"), headers=user.headers).json())
    # 공통 계열에 같은 이름으로 만들면 공통 항목의 다음 버전이 된다
    again = client.post(url("phases"), headers=operator.headers,
                        json={"이름": "운영자 단계", "설명": "d2", "공통": True})
    assert again.json()["버전"] == 2
    assert client.delete(url("phases", made.json()["번호"]), headers=operator.headers).status_code == 200


def test_gimmicks_work_the_same_way(client, headers):
    g1 = create(client, headers, "gimmicks", 조건={"이벤트": "시작"}, 결과={"공지": "시작"})
    g2 = create(client, headers, "gimmicks", 변경내역="공지 문구 변경")
    assert (g1["버전"], g2["버전"]) == (1, 2) and g1["조건"] == {"이벤트": "시작"}
