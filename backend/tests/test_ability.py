"""능력 사용: 능력이 있는 인물의 플레이어가 다른 플레이어를 지목하고, 지목은 게임 변수로 남아 엔딩 조건이 읽는다 (app/default_phases.py ABILITY)."""
from app.default_phases import ABILITY, CHARACTER_SELECT, ENDING
from test_cards import all_pick, answer, block, db, make_scripted_game, players_of, state  # noqa: F401  (픽스처 포함)
from test_endings import api
from test_game import advance


def using(client, make_scripted_game, endings=(), settings=None, content=False):
    def setup(client_, host, wid):
        res = client_.patch(f"/api/works/{wid}/characters/1", headers=host.headers, json={"능력": "한 사람의 정체를 알아낸다"})
        assert res.status_code == 200, res.text
        if content:
            mansion = api(client_, host, wid, "places", 이름="저택")["순서"]
            api(client_, host, wid, "places", 이름="서재", 상위_장소_순서=mansion)
            api(client_, host, wid, "clues", 이름="커터칼", 공개이름="A의 서랍", 내용="날이 부러져 있다")
        for name, condition, text in endings:
            api(client_, host, wid, "endings", 이름=name, 조건=condition, 내용=text)

    cards = [("캐릭터 선택", CHARACTER_SELECT, None), ("능력 사용", ABILITY, settings), ("엔딩", ENDING, None)]
    host, others, room, wid = make_scripted_game(cards, players=3, setup=setup)
    people = players_of(host, others)
    all_pick(client, people)
    assert advance(client, host).status_code == 200
    slots = {who.number: state(client, who).json()["나"]["인물_순서"] for who in people}
    return host, people, {slots[who.number]: who for who in people}


def test_only_the_character_with_an_ability_picks_a_target(client, make_scripted_game):
    host, people, who = using(client, make_scripted_game)
    mine = state(client, who[1]).json()
    assert block(mine, "능력 사용 능력")["내용"] == "한 사람의 정체를 알아낸다"
    box = block(mine, "능력 사용")
    assert box["종류"] == "투표"
    assert [i["이름"] for i in box["항목"] if not i.get("기타")] == ["인물0", "인물1", "인물2"]          # 기본 대상은 플레이어의 인물
    assert [i["이름"] for i in box["항목"] if i.get("기타")] == ["사용 안 함"]
    other = state(client, who[2]).json()
    assert block(other, "능력 사용")["종류"] == "글" and "능력이 없습니다" in block(other, "능력 사용")["내용"]
    assert block(mine, "능력 사용 완료")["전체"] == 1 and block(other, "능력 사용 완료")["완료"] == 0


def test_the_target_is_saved_as_a_variable_that_endings_read(client, make_scripted_game):
    endings = [
        ("2번 지목", {"식": '변수("능력 사용:1") == 2'}, "둘째를 지목했다"),
        ("3번 지목", {"식": '변수("능력 사용:1") == 3'}, "셋째를 지목했다"),
        ("쓰지 않음", {"식": '변수("능력 사용:1") == "사용 안 함"'}, "쓰지 않았다"),
    ]
    host, people, who = using(client, make_scripted_game, endings)
    qid = block(state(client, who[1]).json(), "능력 사용")["질문ID"]
    assert answer(client, who[1], qid, 3).status_code == 200
    assert block(state(client, who[2]).json(), "능력 사용 완료")["완료"] == 1                  # 몇 명이 썼는지만 보인다
    assert answer(client, who[1], qid, 2).status_code == 200                                  # 넘어가기 전에는 바꿀 수 있다
    assert answer(client, who[1], qid, 1).status_code == 200                                  # 자기 자신은 고를 수 없다(무시된다)
    assert advance(client, host).status_code == 200
    shown = sorted(b["이름"] for b in state(client, who[3]).json()["화면"])
    assert shown == ["엔딩: 2번 지목"]


def test_not_using_the_ability_is_also_a_choice(client, make_scripted_game):
    endings = [("쓰지 않음", {"식": '변수("능력 사용:1") == "사용 안 함"'}, "쓰지 않았다")]
    host, people, who = using(client, make_scripted_game, endings)
    qid = block(state(client, who[1]).json(), "능력 사용")["질문ID"]
    assert answer(client, who[1], qid, "사용 안 함").status_code == 200
    assert advance(client, host).status_code == 200
    assert [b["이름"] for b in state(client, who[1]).json()["화면"] if b["이름"].startswith("엔딩")] == ["엔딩: 쓰지 않음"]


def test_targets_can_also_be_places_and_clues(client, make_scripted_game):
    endings = [
        ("서재 지목", {"식": '변수("능력 사용:1") == "장소:2"'}, "서재를 지목했다"),
        ("서랍 지목", {"식": '변수("능력 사용:1") == "단서:1"'}, "서랍을 지목했다"),
    ]
    host, people, who = using(client, make_scripted_game, endings, settings={"대상": ["인물", "장소", "단서"]}, content=True)
    box = block(state(client, who[1]).json(), "능력 사용")
    names = {(i["종류"], i["이름"]) for i in box["항목"]}
    assert {("인물", "인물0"), ("장소", "저택"), ("장소", "저택 › 서재"), ("단서", "A의 서랍"), ("기타", "사용 안 함")} <= names   # 단서는 공개이름으로 보인다
    assert "커터칼" not in str(box)
    values = {i["이름"]: i["값"] for i in box["항목"]}
    assert values["저택 › 서재"] == "장소:2" and values["A의 서랍"] == "단서:1"
    assert answer(client, who[1], box["질문ID"], "장소:2").status_code == 200
    assert answer(client, who[1], box["질문ID"], "단서:1").status_code == 200
    assert answer(client, who[1], box["질문ID"], "단서:9").status_code == 200              # 없는 대상은 무시된다
    assert advance(client, host).status_code == 200
    assert [b["이름"] for b in state(client, who[1]).json()["화면"] if b["이름"].startswith("엔딩")] == ["엔딩: 서랍 지목"]


def test_places_and_clues_are_not_offered_unless_the_card_setting_asks(client, make_scripted_game):
    host, people, who = using(client, make_scripted_game, content=True)
    assert {i["종류"] for i in block(state(client, who[1]).json(), "능력 사용")["항목"]} == {"인물", "기타"}
