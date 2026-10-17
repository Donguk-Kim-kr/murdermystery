"""페이즈 끼워 넣기·옮기기·지우기(phases.py)와 카드 표시 이름: 칸 번호는 그대로 두고 내용을 옮긴다."""
import psycopg

from test_content import add, url, work


def phases_url(w, *parts):
    return f"/api/works/{w}/phases" + "".join(f"/{p}" for p in parts)


def library_phase(client, headers, name):
    res = client.post("/api/library/phases", headers=headers, json={"이름": name, "설명": "d", "규칙": {}})
    assert res.status_code == 201, res.text
    return res.json()["번호"]


def layout(client, headers, w):
    """위치 순서대로 [(칸 번호, 이름, 시간, [카드 표시이름...])]."""
    bundle = client.get(f"/api/works/{w}/content", headers=headers).json()
    cards = {}
    for c in bundle["phase-steps"]:
        cards.setdefault(c["진행순서_순서"], []).append(c["표시이름"])
    return [(p["순서"], p["이름"], p["진행시간"], cards.get(p["순서"], [])) for p in bundle["phases"]]


def setup(client, headers):
    """칸 3개: 1=도입(카드 A), 2=조사(카드 B, 투표), 3=결말(카드 C)."""
    w = work(client, headers)
    ids = {n: library_phase(client, headers, f"카드{n}") for n in "ABC"}
    for i, (name, card) in enumerate((("도입", "A"), ("조사", "B"), ("결말", "C")), 1):
        add(client, headers, w, "phases", 이름=name, 진행시간=i * 10)
        add(client, headers, w, "phase-steps", 진행순서_순서=i, 진행단계_번호=ids[card])
    return w, ids


def test_phase_name_and_settings_are_saved_and_optional(client, headers):
    w = work(client, headers)
    assert add(client, headers, w, "phases")["이름"] is None
    p = add(client, headers, w, "phases", 이름="토론")
    assert p["이름"] == "토론"
    card = library_phase(client, headers, "토론 카드")
    step = add(client, headers, w, "phase-steps", 진행순서_순서=1, 진행단계_번호=card)
    assert step["설정"] is None
    res = client.patch(url(w, "phase-steps", step["번호"]), headers=headers, json={"설정": {"내용유지": False}})
    assert res.status_code == 200 and res.json()["설정"] == {"내용유지": False}
    res = client.patch(url(w, "phase-steps", step["번호"]), headers=headers, json={"설정": None})
    assert res.json()["설정"] is None                      # 비우면 정의의 기본값을 쓴다
    assert client.patch(url(w, "phase-steps", step["번호"]), headers=headers, json={"설정": "문자"}).status_code == 422


def test_insert_shifts_later_phases_and_keeps_their_contents(client, headers):
    w, _ = setup(client, headers)
    vote = add(client, headers, w, "votes", 진행순서_순서=2, 이름="범인 투표", 내용="c")
    res = client.post(phases_url(w, "insert"), headers=headers, json={"position": 2, "이름": "밀담", "진행시간": 5})
    assert res.status_code == 201, res.text
    assert [(p["이름"], p["진행시간"]) for p in res.json()["phases"]] == [
        ("도입", 10), ("밀담", 5), ("조사", 20), ("결말", 30)
    ]
    assert [(r[1], r[3]) for r in layout(client, headers, w)] == [
        ("도입", ["카드A"]), ("밀담", []), ("조사", ["카드B"]), ("결말", ["카드C"])
    ]
    # 투표는 '조사'를 따라 움직였다
    votes = client.get(url(w, "votes"), headers=headers).json()
    slot_of = {p[1]: p[0] for p in layout(client, headers, w)}
    assert votes[0]["순서"] == vote["순서"] and votes[0]["진행순서_순서"] == slot_of["조사"]


def test_insert_at_ends_and_out_of_range(client, headers):
    w, _ = setup(client, headers)
    assert client.post(phases_url(w, "insert"), headers=headers, json={"position": 1, "이름": "앞"}).status_code == 201
    assert client.post(phases_url(w, "insert"), headers=headers, json={"position": 5, "이름": "뒤"}).status_code == 201
    assert [r[1] for r in layout(client, headers, w)] == ["앞", "도입", "조사", "결말", "뒤"]
    assert client.post(phases_url(w, "insert"), headers=headers, json={"position": 7}).status_code == 422
    assert client.post(phases_url(w, "insert"), headers=headers, json={"position": 0}).status_code == 422


def test_move_up_down_and_far(client, headers):
    w, _ = setup(client, headers)
    first = layout(client, headers, w)[0][0]
    assert client.post(phases_url(w, first, "move"), headers=headers, json={"position": 3}).status_code == 200
    assert [(r[1], r[2], r[3]) for r in layout(client, headers, w)] == [
        ("조사", 20, ["카드B"]), ("결말", 30, ["카드C"]), ("도입", 10, ["카드A"])
    ]
    last = layout(client, headers, w)[2][0]
    assert client.post(phases_url(w, last, "move"), headers=headers, json={"position": 1}).status_code == 200
    assert [r[1] for r in layout(client, headers, w)] == ["도입", "조사", "결말"]
    assert client.post(phases_url(w, last, "move"), headers=headers, json={"position": 2}).status_code == 200
    assert [r[1] for r in layout(client, headers, w)] == ["도입", "결말", "조사"]
    assert client.post(phases_url(w, last, "move"), headers=headers, json={"position": 9}).status_code == 422
    assert client.post(phases_url(w, 99, "move"), headers=headers, json={"position": 1}).status_code == 404


def test_move_keeps_gimmicks_votes_and_media_with_their_phase(client, headers):
    w, _ = setup(client, headers)
    gimmick = client.post("/api/library/gimmicks", headers=headers, json={"이름": "독", "조건": {}, "결과": {}}).json()["번호"]
    add(client, headers, w, "gimmick-uses", 기믹_번호=gimmick, 진행순서_순서=1, 설정={"횟수": 2})
    add(client, headers, w, "votes", 진행순서_순서=1, 이름="v", 내용="c")
    add(client, headers, w, "materials", 제목="자료", 내용="내용")
    first = layout(client, headers, w)[0][0]
    assert client.post(phases_url(w, first, "move"), headers=headers, json={"position": 3}).status_code == 200
    assert [r[1] for r in layout(client, headers, w)] == ["조사", "결말", "도입"]
    slot_of = {p[1]: p[0] for p in layout(client, headers, w)}
    use = client.get(url(w, "gimmick-uses"), headers=headers).json()[0]
    assert use["진행순서_순서"] == slot_of["도입"] and use["설정"] == {"횟수": 2}
    assert client.get(url(w, "votes"), headers=headers).json()[0]["진행순서_순서"] == slot_of["도입"]


def test_delete_pulls_later_phases_forward_and_drops_cards(client, headers):
    w, _ = setup(client, headers)
    second = layout(client, headers, w)[1][0]
    res = client.delete(phases_url(w, second), headers=headers)
    assert res.status_code == 200, res.text
    assert [(r[1], r[2], r[3]) for r in layout(client, headers, w)] == [("도입", 10, ["카드A"]), ("결말", 30, ["카드C"])]
    # 칸 번호에 빈틈이 생겨도 위치로 다룬다
    assert client.post(phases_url(w, "insert"), headers=headers, json={"position": 3, "이름": "끝"}).status_code == 201
    assert [r[1] for r in layout(client, headers, w)] == ["도입", "결말", "끝"]


def test_delete_is_blocked_while_gimmick_vote_or_media_is_attached(client, headers):
    w, _ = setup(client, headers)
    add(client, headers, w, "votes", 진행순서_순서=2, 이름="v", 내용="c")
    before = layout(client, headers, w)
    res = client.delete(phases_url(w, 2), headers=headers)
    assert res.status_code == 409 and "투표" in res.json()["detail"]
    assert layout(client, headers, w) == before            # 아무것도 바뀌지 않았다


def test_delete_the_only_phase(client, headers):
    w = work(client, headers)
    add(client, headers, w, "phases")
    assert client.delete(phases_url(w, 1), headers=headers).json() == {"phases": []}


def test_card_display_names_number_repeated_cards_by_position(client, headers):
    w = work(client, headers)
    inv = library_phase(client, headers, "조사")
    talk = library_phase(client, headers, "토론")
    for _ in range(3):
        add(client, headers, w, "phases")
    add(client, headers, w, "phase-steps", 진행순서_순서=3, 진행단계_번호=inv)      # 나중에 만들었지만 뒤쪽 칸
    add(client, headers, w, "phase-steps", 진행순서_순서=1, 진행단계_번호=inv)
    add(client, headers, w, "phase-steps", 진행순서_순서=2, 진행단계_번호=talk)
    names = {(c["진행순서_순서"], c["표시이름"]) for c in client.get(f"/api/works/{w}/content", headers=headers).json()["phase-steps"]}
    assert names == {(1, "1차 조사"), (2, "토론"), (3, "2차 조사")}
    # 앞에 한 칸을 끼워 넣어 카드가 한 칸씩 밀려도, 위치 순서대로 번호가 매겨진다
    client.post(phases_url(w, "insert"), headers=headers, json={"position": 1})
    again = {c["표시이름"] for c in client.get(f"/api/works/{w}/content", headers=headers).json()["phase-steps"]}
    assert again == {"1차 조사", "토론", "2차 조사"}


def test_only_the_owner_can_reorder(client, new_user):
    owner, other = new_user(), new_user()
    w = work(client, owner)
    add(client, owner, w, "phases")
    assert client.post(phases_url(w, "insert"), headers=other, json={"position": 1}).status_code == 404
    assert client.post(phases_url(w, 1, "move"), headers=other, json={"position": 1}).status_code == 404
    assert client.delete(phases_url(w, 1), headers=other).status_code == 404
    assert client.post(phases_url(w, "insert"), json={"position": 1}).status_code == 401


def test_snapshot_carries_names_settings_and_display_names(client, headers, test_dbname):
    w, ids = setup(client, headers)
    add(client, headers, w, "phase-steps", 진행순서_순서=3, 진행단계_번호=ids["A"], 설정={"내용유지": False})
    client.post(f"/api/works/{w}/characters", headers=headers, json={"이름": "A"})
    res = client.post(f"/api/works/{w}/confirm", headers=headers, json={})
    assert res.status_code == 201, res.text
    with psycopg.connect(dbname=test_dbname) as conn:
        snap = conn.execute('SELECT "시나리오" FROM "버전" WHERE "작품_번호" = %s', (w,)).fetchone()[0]
    assert [p["이름"] for p in snap["진행순서"]] == ["도입", "조사", "결말"]
    cards = {(c["진행순서_순서"], c["진행단계_번호"]): c for c in snap["진행구성"]}
    assert cards[(1, ids["A"])]["표시이름"] == "1차 카드A" and cards[(3, ids["A"])]["표시이름"] == "2차 카드A"
    assert cards[(3, ids["A"])]["설정"] == {"내용유지": False} and cards[(2, ids["B"])]["표시이름"] == "카드B"


def bundle(client, headers, w):
    return client.get(f"/api/works/{w}/content", headers=headers).json()


def test_phase_name_follows_its_cards_unless_the_author_names_it(client, headers):
    w = work(client, headers)
    inv, talk = library_phase(client, headers, "조사"), library_phase(client, headers, "밀담")
    add(client, headers, w, "phases")
    add(client, headers, w, "phases", 이름="자유 시간")
    assert [p["표시이름"] for p in bundle(client, headers, w)["phases"]] == [None, "자유 시간"]       # 카드가 없으면 이름 없음
    add(client, headers, w, "phase-steps", 진행순서_순서=1, 진행단계_번호=inv)
    assert bundle(client, headers, w)["phases"][0]["표시이름"] == "조사"
    add(client, headers, w, "phase-steps", 진행순서_순서=1, 진행단계_번호=talk)
    first = bundle(client, headers, w)["phases"][0]
    assert first["이름"] is None and first["표시이름"] == "조사·밀담"                                    # 따라가는 이름은 저장하지 않는다
    add(client, headers, w, "phase-steps", 진행순서_순서=2, 진행단계_번호=inv)
    assert bundle(client, headers, w)["phases"][1]["표시이름"] == "자유 시간"                            # 정한 이름이 우선


def test_clearing_the_name_makes_the_phase_follow_its_cards_again(client, headers):
    w = work(client, headers)
    inv = library_phase(client, headers, "조사")
    add(client, headers, w, "phases", 이름="내 이름")
    add(client, headers, w, "phase-steps", 진행순서_순서=1, 진행단계_번호=inv)
    assert bundle(client, headers, w)["phases"][0]["표시이름"] == "내 이름"
    assert client.patch(url(w, "phases", 1), headers=headers, json={"이름": None}).status_code == 200
    assert bundle(client, headers, w)["phases"][0]["표시이름"] == "조사"
    client.patch(url(w, "phases", 1), headers=headers, json={"이름": "   "})                           # 공백뿐이어도 따라간다
    assert bundle(client, headers, w)["phases"][0]["표시이름"] == "조사"


def test_snapshot_carries_phase_display_names(client, headers, test_dbname):
    w, ids = setup(client, headers)
    add(client, headers, w, "phase-steps", 진행순서_순서=2, 진행단계_번호=ids["A"])
    client.post(f"/api/works/{w}/characters", headers=headers, json={"이름": "A"})
    assert client.post(f"/api/works/{w}/confirm", headers=headers, json={}).status_code == 201
    with psycopg.connect(dbname=test_dbname) as conn:
        snap = conn.execute('SELECT "시나리오" FROM "버전" WHERE "작품_번호" = %s', (w,)).fetchone()[0]
    assert [(p["이름"], p["표시이름"]) for p in snap["진행순서"]] == [("도입", "도입"), ("조사", "조사"), ("결말", "결말")]
    p2 = add(client, headers, w, "phases")["순서"]                                                  # 이름 없는 페이즈는 카드 이름을 따라간다
    add(client, headers, w, "phase-steps", 진행순서_순서=p2, 진행단계_번호=ids["A"])
    add(client, headers, w, "phase-steps", 진행순서_순서=p2, 진행단계_번호=ids["B"])
    client.post(f"/api/works/{w}/confirm", headers=headers, json={})
    with psycopg.connect(dbname=test_dbname) as conn:
        snap = conn.execute('SELECT "시나리오" FROM "버전" WHERE "작품_번호" = %s ORDER BY "번호" DESC LIMIT 1', (w,)).fetchone()[0]
    assert snap["진행순서"][-1]["이름"] is None and snap["진행순서"][-1]["표시이름"] == "3차 카드A·2차 카드B"   # 같은 카드가 여럿이면 1차·2차 이름을 그대로 잇는다
