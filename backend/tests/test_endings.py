"""엔딩·후일담: 조건 식으로 결과를 가른다 (app/default_phases.py ENDING·EPILOGUE, 게임 변수, 투표 결과)."""
import pytest

from app.default_phases import CHARACTER_SELECT, ENDING, EPILOGUE, FINAL_VOTE
from test_cards import all_pick, answer, block, db, make_scripted_game, players_of, state, tab  # noqa: F401  (픽스처 포함)
from test_game import advance

SET_FLAG = '''
def 실행(카드):
    변수설정("비밀알아챔", 카드.설정.get("값", False))
    변수설정("점수", 3)
'''


def api(client, host, wid, kind, **body):
    res = client.post(f"/api/works/{wid}/content/{kind}", headers=host.headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def play(client, make_scripted_game, endings, epilogues=(), votes=None, flag=None, players=3, extra_cards=(), unchecked=None, setup_extra=None):
    """캐릭터 선택 → 최종 투표 → (변수 정하기) → 엔딩 → 후일담. `votes(people, slots)` 가 투표를 한다."""
    holder = {}

    def setup(client_, host, wid):
        holder["wid"] = wid
        if setup_extra:
            setup_extra(client_, host, wid)
        for name, condition, text in endings:
            api(client_, host, wid, "endings", 이름=name, 조건=condition, 내용=text)
        for person, condition, text in epilogues:
            body = {"내용": text}
            if person is not None:
                body["인물_순서"] = person
            if condition is not None:
                body["조건"] = condition
            api(client_, host, wid, "epilogues", **body)

    cards = [("캐릭터 선택", CHARACTER_SELECT, None), ("최종 투표", FINAL_VOTE, {"후보": [1, 2, 3, "사고사"]})]
    if flag is not None:
        cards.append(("변수", SET_FLAG, {"값": flag}))
    cards += [("엔딩", ENDING, None), ("후일담", EPILOGUE, None), *extra_cards]
    def edit(scenario):
        for row in scenario["엔딩분기"]:
            if unchecked and row["이름"] in unchecked:
                row["조건"] = unchecked[row["이름"]]

    host, others, room, wid = make_scripted_game(cards, players=players, setup=setup, edit=edit if unchecked else None)
    people = players_of(host, others)
    all_pick(client, people)
    assert advance(client, host).status_code == 200
    slots = {who.number: state(client, who).json()["나"]["인물_순서"] for who in people}
    if votes:
        votes(people, slots)
    return host, people, slots


def cast(client, who, value):
    box = block(state(client, who).json(), "최종 투표")
    assert answer(client, who, box["질문ID"], value).status_code == 200


def go_to_endings(client, host, steps):
    for _ in range(steps):
        assert advance(client, host).status_code == 200


def titles(client, who):
    return sorted(b["이름"] for b in state(client, who).json()["화면"])


def test_ending_branch_is_chosen_by_the_vote_result(client, make_scripted_game):
    arrested = '결과_인물("최종 투표") is not None and 결과_인물("최종 투표").이름 == "인물0"'
    endings = [("A 구속", {"식": arrested}, "범인이 잡혔습니다."), ("A 구속 실패", {"식": "not (" + arrested + ")"}, "범인이 달아났습니다.")]

    def votes(people, slots):
        by_name = {state(client, people[0]).json()["인물"][i]["이름"]: state(client, people[0]).json()["인물"][i]["순서"] for i in range(3)}
        cast(client, people[1], by_name["인물0"])
        cast(client, people[2], by_name["인물0"])

    host, people, _ = play(client, make_scripted_game, endings, votes=votes)
    go_to_endings(client, host, 1)                                             # 투표 → 엔딩
    assert titles(client, people[1]) == ["엔딩: A 구속"]
    assert block(state(client, people[1]).json(), "엔딩: A 구속")["내용"] == "범인이 잡혔습니다."


def test_ending_branch_for_a_failed_arrest_and_for_a_non_character_result(client, make_scripted_game):
    endings = [
        ("잡힘", {"식": '결과_인물("최종 투표") is not None'}, "누군가 구속됨"),
        ("사고사", {"식": '결과_기타("최종 투표") == "사고사"'}, "사고였습니다."),
        ("없음", {"식": '결과("최종 투표") is None'}, "아무도 구속되지 않음"),
    ]

    def votes(people, slots):
        cast(client, people[0], "사고사")
        cast(client, people[1], "사고사")
        cast(client, people[2], slots[people[0].number])

    host, people, _ = play(client, make_scripted_game, endings, votes=votes)
    go_to_endings(client, host, 1)
    assert titles(client, people[0]) == ["엔딩: 사고사"]

    host2, people2, _ = play(client, make_scripted_game, endings)               # 투표가 없다
    go_to_endings(client, host2, 1)
    assert titles(client, people2[0]) == ["엔딩: 없음"]


def test_all_matching_branches_are_shown_in_order_and_an_empty_condition_always_shows(client, make_scripted_game):
    endings = [
        ("항상", {}, "기본 이야기"),
        ("첫째", {"식": "True"}, "하나"),
        ("거짓", {"식": "False"}, "안 보임"),
        ("셋째", {"식": "1 + 1 == 2"}, "셋"),
    ]
    host, people, _ = play(client, make_scripted_game, endings)
    go_to_endings(client, host, 1)
    assert titles(client, people[0]) == ["엔딩: 셋째", "엔딩: 첫째", "엔딩: 항상"]      # 정렬한 이름(보이는 순서는 분기 순서)
    shown = [b["이름"] for b in state(client, people[0]).json()["화면"]]
    assert shown == ["엔딩: 항상", "엔딩: 첫째", "엔딩: 셋째"]                          # 분기 순서대로


def test_conditions_read_game_variables_set_by_scripts(client, make_scripted_game):
    endings = [
        ("알아챔", {"식": '변수("비밀알아챔") == True'}, "비밀을 알았다"),
        ("모름", {"식": '변수("비밀알아챔") != True'}, "비밀을 몰랐다"),
        ("점수", {"식": '변수("점수", 0) >= 3'}, "점수 충분"),
    ]
    host, people, _ = play(client, make_scripted_game, endings, flag=True)
    go_to_endings(client, host, 2)                                              # 투표 → 변수 → 엔딩
    assert titles(client, people[0]) == ["엔딩: 알아챔", "엔딩: 점수"]
    host2, people2, _ = play(client, make_scripted_game, endings, flag=False)
    go_to_endings(client, host2, 2)
    assert titles(client, people2[0]) == ["엔딩: 모름", "엔딩: 점수"]


def test_conditions_can_read_who_holds_a_clue_and_which_player_has_a_character(client, make_scripted_game):
    endings = [
        ("단서 없음", {"식": '단서_보유자("없는 단서") is None'}, "아무도 가지지 않음"),
        ("인물 확인", {"식": '인물의_플레이어(인물찾기(1)) is not None and 인물찾기(1).목표 is None'}, "인물 1 은 플레이어가 맡음"),
    ]
    host, people, _ = play(client, make_scripted_game, endings)
    go_to_endings(client, host, 1)
    assert titles(client, people[0]) == ["엔딩: 단서 없음", "엔딩: 인물 확인"]


def test_epilogues_show_per_character_with_conditions_and_without(client, make_scripted_game):
    epilogues = [
        (None, None, "모두의 후일담"),
        (1, {"식": '변수("비밀알아챔") == True'}, "인물1 의 이후"),
        (2, {"식": '변수("비밀알아챔") == False'}, "인물2 의 이후"),
    ]
    host, people, _ = play(client, make_scripted_game, [("끝", {}, "끝")], epilogues=epilogues, flag=True)
    go_to_endings(client, host, 3)                                              # 투표 → 변수 → 엔딩 → 후일담
    view = state(client, people[0]).json()
    names = [b["이름"] for b in view["화면"]]
    assert names == ["후일담 1", "후일담 2: 인물0"]                                 # 인물2 의 후일담은 조건이 맞지 않는다
    assert any(t["이름"] == "엔딩: 끝" for t in view["탭"])                         # 앞 단계의 탭은 남는다


def test_broken_conditions_do_not_stop_the_game_and_are_reported_to_the_host_only(client, make_scripted_game):
    broken = {"깨짐": {"식": "몰라()"}, "글자 아님": {"식": 5}, "나누기": {"식": "1 / 0"}, "모양": {"조건": "x"}}
    endings = [(name, {"식": "True"}, "x") for name in broken] + [("정상", {"식": "True"}, "정상 엔딩")]
    host, people, _ = play(client, make_scripted_game, endings, unchecked=broken)      # 확정 검사는 통과한 뒤 스냅샷만 깨뜨린다
    go_to_endings(client, host, 1)
    assert titles(client, people[1]) == ["엔딩: 정상"]
    assert state(client, people[1]).json()["오류"] == []
    assert state(client, host).json()["오류"]                                       # 방장은 무엇이 잘못인지 본다


def test_conditions_cannot_change_the_game(client, make_scripted_game):
    bad = {"바꾸기": {"식": '변수설정("x", 1) is None'}}
    host, people, _ = play(client, make_scripted_game, [("바꾸기", {"식": "True"}, "x")], unchecked=bad)
    go_to_endings(client, host, 1)
    assert titles(client, people[0]) == []                                          # 조건 안에서는 상태를 바꾸는 함수를 쓸 수 없다
    assert any("알 수 없는 이름" in e["메시지"] for e in state(client, host).json()["오류"])


def test_game_variables_are_limited_and_isolated(client, make_scripted_game):
    big = "def 실행(카드):\n    변수설정('큰', '가' * 3000)\n"
    host, others, _, _ = make_scripted_game([("큰 변수", big, None)])
    assert "너무 큽니다" in state(client, host).json()["오류"][0]["메시지"]
    copy = "def 실행(카드):\n    변수설정('목록', [1])\n    값 = 변수('목록')\n    값.append(2)\n    모두.보이기(글('길이', str(len(변수('목록')))))\n"
    host2, _, _, _ = make_scripted_game([("복사", copy, None)])
    assert block(state(client, host2).json(), "길이")["내용"] == "1"                 # 받은 값을 바꿔도 변수는 그대로


def test_reveal_all_ends_the_game_and_shows_every_clue_and_every_narrative(client, make_scripted_game, db):
    from app.default_phases import REVEAL_ALL
    from test_investigation import build

    host, others, room, wid = make_scripted_game([("전체 공개", REVEAL_ALL, None)], setup=build)
    view = state(client, others[0]).json()
    assert view["종료"] is True
    assert "게임이 끝났습니다" in block(view, "게임 종료")["내용"]
    cards = tab(view, "전체 단서")["항목"]
    assert sorted(c["이름"] for c in cards) == sorted(["찢어진 편지", "깨진 안경", "독이 든 컵", "정원사의 증언", "집사의 증언"])
    story = tab(view, "전체 서사")["내용"]
    for i in range(3):
        assert f"인물{i}\n{i}번의 서사 하나\n\n{i}번의 서사 둘" in story                      # 모든 인물의 서사가 모든 부분으로
    assert db.execute('SELECT "상태" FROM "진행" WHERE "방_번호" = %s', (room["번호"],)).fetchone()[0] == "종료"
    assert advance(client, host).status_code == 409                                        # 끝난 게임은 더 진행하지 않는다


def test_ending_condition_arrested_the_culprit_by_vote(client, make_scripted_game):
    """"투표로 범인을 검거했다": 최다 득표가 인물이고 그 인물이 범인으로 표시되어 있다."""
    caught = '결과_인물("최종 투표") is not None and 결과_인물("최종 투표").범인'
    endings = [("검거", {"식": caught}, "범인을 검거했습니다."), ("검거 실패", {"식": "not (" + caught + ")"}, "범인이 달아났습니다.")]

    def mark_culprit(client_, host, wid):
        res = client_.patch(f"/api/works/{wid}/characters/1", headers=host.headers, json={"범인": True})
        assert res.status_code == 200, res.text

    def run(target_order):
        def votes(people, slots):
            by_name = {p["이름"]: p["순서"] for p in state(client, people[0]).json()["인물"]}
            for who in people[1:]:
                cast(client, who, by_name[target_order])
        return votes

    for target, expected in (("인물0", "범인을 검거했습니다."), ("인물1", "범인이 달아났습니다.")):
        host, people, _ = play(client, make_scripted_game, endings, votes=run(target), setup_extra=mark_culprit)
        go_to_endings(client, host, 1)
        shown = [b for b in state(client, people[0]).json()["화면"] if b["이름"].startswith("엔딩")]
        assert [b["내용"] for b in shown] == [expected], target


def test_tie_is_its_own_ending_and_not_a_failed_arrest(client, make_scripted_game):
    """동률이면 '검거'도 '검거 실패'도 아니고 '동률' 분기만 나온다."""
    vote = "'최종 투표'"
    caught = f"결과_인물({vote}) is not None and 결과_인물({vote}).범인"
    endings = [
        ("검거", {"식": caught}, "검거"),
        ("동률", {"식": f"len(최다득표({vote})) > 1"}, "동률"),
        ("투표 없음", {"식": f"투표수({vote}) == 0"}, "투표 없음"),
        ("검거 실패", {"식": f"결과({vote}) is not None and not ({caught})"}, "검거 실패"),
    ]

    def mark_culprit(client_, host, wid):
        assert client_.patch(f"/api/works/{wid}/characters/1", headers=host.headers, json={"범인": True}).status_code == 200

    def scenario(picks):
        def votes(people, slots):
            by_name = {p["이름"]: p["순서"] for p in state(client, people[0]).json()["인물"]}
            for who, choice in zip(people, picks):
                if choice is not None:
                    cast(client, who, by_name.get(choice, choice))
        return votes

    for expected, picks in (
        ("동률", ("인물1", "인물0", "사고사")),
        ("투표 없음", (None, None, None)),
        ("검거 실패", ("사고사", "사고사", "사고사")),
    ):
        host, people, slots = play(client, make_scripted_game, endings, votes=scenario(picks), setup_extra=mark_culprit)
        go_to_endings(client, host, 1)
        shown = [b["내용"] for b in state(client, people[0]).json()["화면"] if b["이름"].startswith("엔딩")]
        assert shown == [expected], (expected, shown)


def test_conditions_declared_by_the_final_vote_phase_work_as_written(client, make_scripted_game):
    """최종 투표 진행단계가 스스로 내놓은 조건(조건정의)의 식을 그대로 엔딩 조건으로 써서 동작을 확인한다."""
    import re
    from app.cards import known_names
    from app.declare import declarations
    from app.default_phases import FINAL_VOTE

    declared = {c["이름"]: c for c in declarations(FINAL_VOTE, known_names())["조건"]}
    plain = ["범인을 검거했다", "범인이 아닌 쪽으로 결과가 났다(검거 실패)", "동률이다", "아무도 투표하지 않았다"]
    endings = [(name, {"식": declared[name]["식"]}, name) for name in plain]
    # 인자가 있는 조건은 자리표시자를 채워서 쓴다: 인물 1(범인)이 가장 많은 표
    endings.append(("인물 지목", {"식": re.sub(r"\{인물\}", "1", declared["이 인물이 가장 많은 표를 받았다"]["식"])}, "인물 지목"))

    def mark_culprit(client_, host, wid):
        assert client_.patch(f"/api/works/{wid}/characters/1", headers=host.headers, json={"범인": True}).status_code == 200

    def votes(picks):
        def run(people, slots):
            by_name = {p["이름"]: p["순서"] for p in state(client, people[0]).json()["인물"]}
            for who, choice in zip(people, picks):
                if choice is not None:
                    cast(client, who, by_name.get(choice, choice))
        return run

    for picks, expected in (
        ((None, "인물0", "인물0"), ["범인을 검거했다", "인물 지목"]),
        ((None, "인물1", "인물1"), ["범인이 아닌 쪽으로 결과가 났다(검거 실패)"]),
        (("인물1", "인물0", "사고사"), ["동률이다"]),
        ((None, None, None), ["아무도 투표하지 않았다"]),
    ):
        host, people, _ = play(client, make_scripted_game, endings, votes=votes(picks), setup_extra=mark_culprit)
        go_to_endings(client, host, 1)
        shown = [b["내용"] for b in state(client, people[0]).json()["화면"] if b["이름"].startswith("엔딩")]
        assert shown == expected, (picks, shown)
