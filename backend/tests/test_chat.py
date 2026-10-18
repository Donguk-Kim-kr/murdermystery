"""게임 채팅: 장소(전체·밀담), 위치, 받는 사람, 관전자 (app/chat.py)."""
from tests.test_cards import PROLOGUE, db, make_scripted_game  # noqa: F401  (픽스처)
from tests.test_game import state  # noqa: F401


def chat(client, who, after=0):
    return client.get("/api/game/me/chat", headers=who.headers, params={"after": after})


def move(client, who, place):
    return client.post("/api/game/me/chat/move", headers=who.headers, json={"장소": place})


def say(client, who, text):
    return client.post("/api/game/me/chat/send", headers=who.headers, json={"내용": text})


def texts(client, who, place=None, after=0):
    return [m["내용"] for m in chat(client, who, after).json()["메시지"] if place is None or m["장소"] == place]


def game4(make_scripted_game, **kw):
    host, others, _, _ = make_scripted_game([("프롤로그", PROLOGUE, None)], players=4, **kw)
    return host, others


def test_everyone_starts_in_the_public_place_and_places_follow_the_player_count(client, make_scripted_game):
    host, others = game4(make_scripted_game)
    body = chat(client, host).json()
    assert [r["이름"] for r in body["장소들"]] == ["전체", "밀담 A", "밀담 B"]            # 4인이면 밀담 장소가 둘
    assert body["내_위치"] == "전체" and body["역할"] == "플레이어"
    assert len(body["장소들"][0]["사람들"]) == 4 and body["장소들"][1]["사람들"] == []
    assert body["장소들"][1]["최대인원"] == 2 and body["장소들"][0]["최대인원"] is None
    host3, _ = make_scripted_game([("프롤로그", PROLOGUE, None)], players=3)[:2]
    assert [r["이름"] for r in chat(client, host3).json()["장소들"]] == ["전체", "밀담 A"]


def test_public_message_reaches_every_player_and_is_saved(client, make_scripted_game, db):
    host, others = game4(make_scripted_game)
    assert say(client, others[0], "안녕하세요").status_code == 200
    for who in (host, *others):
        assert texts(client, who) == ["안녕하세요"]
    assert db.execute('SELECT count(*) FROM "대화"').fetchone()[0] >= 1
    sent = chat(client, host).json()["메시지"][0]
    assert sent["장소"] == "전체" and sent["보낸이"]["계정_번호"] == others[0].number and sent["보낸이"]["인물_이름"] is None


def test_secret_place_message_is_seen_only_by_those_inside(client, make_scripted_game):
    host, others = game4(make_scripted_game)
    a, b, c = others
    assert move(client, a, "밀담 A").status_code == 200 and move(client, b, "밀담 A").status_code == 200
    assert say(client, a, "비밀 이야기").status_code == 200
    assert texts(client, a) == ["비밀 이야기"] and texts(client, b) == ["비밀 이야기"]
    assert texts(client, host) == [] and texts(client, c) == []                       # 밖에 있는 사람은 받지 못한다
    places = {r["이름"]: [p["계정_번호"] for p in r["사람들"]] for r in chat(client, host).json()["장소들"]}
    assert sorted(places["밀담 A"]) == sorted([a.number, b.number]) and places["전체"] and a.number not in places["전체"]    # 위치는 모두에게 보인다


def test_secret_place_holds_two_people_only(client, make_scripted_game):
    host, others = game4(make_scripted_game)
    for who in others[:2]:
        assert move(client, who, "밀담 A").status_code == 200
    res = move(client, others[2], "밀담 A")
    assert res.status_code == 409 and "두 사람" in res.json()["detail"]
    assert chat(client, others[2]).json()["내_위치"] == "전체"
    assert move(client, others[2], "밀담 B").status_code == 200                       # 다른 빈 장소는 된다
    assert move(client, others[2], "밀담 C").status_code == 422


def test_messages_while_away_or_before_arrival_are_never_seen(client, make_scripted_game):
    host, others = game4(make_scripted_game)
    a, b, _ = others
    say(client, host, "처음 전체")
    move(client, a, "밀담 A")
    say(client, host, "a 가 없는 동안")
    say(client, a, "혼자 있는 밀담")
    move(client, b, "밀담 A")                                                         # b 는 나중에 들어온다
    say(client, a, "둘이 있는 밀담")
    assert texts(client, b, "밀담 A") == ["둘이 있는 밀담"]                              # 들어오기 전의 밀담은 보이지 않는다
    move(client, a, "전체")
    assert texts(client, a) == ["처음 전체", "혼자 있는 밀담", "둘이 있는 밀담"]        # 있었던 동안 받은 것은 남는다
    assert "a 가 없는 동안" not in texts(client, a)                                    # 자리를 비운 동안의 전체 대화는 영영 보이지 않는다
    assert "a 가 없는 동안" in texts(client, host)


def test_incremental_read_returns_only_newer_messages(client, make_scripted_game):
    host, others = game4(make_scripted_game)
    say(client, host, "하나")
    first = chat(client, host).json()["메시지"]
    say(client, host, "둘")
    assert texts(client, host, after=first[-1]["번호"]) == ["둘"]


def test_message_must_be_one_to_five_hundred_characters(client, make_scripted_game):
    host, _ = game4(make_scripted_game)
    assert say(client, host, "   ").status_code == 422
    assert say(client, host, "가" * 501).status_code == 422
    assert say(client, host, "가" * 500).status_code == 200


def test_observers_read_but_cannot_write_and_gm_reads_secret_places(client, make_scripted_game):
    host, others = game4(make_scripted_game, watcher_modes=("GM", "일반"))
    gm, normal = make_scripted_game.watchers
    say(client, host, "공개 말")
    move(client, others[0], "밀담 A")
    move(client, others[1], "밀담 A")
    say(client, others[0], "속닥속닥")
    assert texts(client, normal) == ["공개 말"]                                         # 일반 관전: 전체만
    assert texts(client, gm) == ["공개 말", "속닥속닥"]                                  # GM 관전: 밀담까지
    assert chat(client, gm).json()["역할"] == "GM 관전" and chat(client, normal).json()["역할"] == "일반 관전"
    assert chat(client, gm).json()["내_위치"] is None
    for who in (gm, normal):                                                          # 위치는 보지만 쓰거나 옮기지는 못한다
        assert len(chat(client, who).json()["장소들"]) == 3
        assert say(client, who, "참견").status_code == 403
        assert move(client, who, "밀담 B").status_code == 403


def test_chat_requires_a_running_game(client, make_account):
    assert chat(client, make_account()).status_code == 404
