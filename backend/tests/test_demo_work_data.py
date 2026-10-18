"""시연용 샘플 작품의 내용이 제작 규칙 안에 들어가는지(app/demo_work.py)."""
from app import narrative
from app.demo_work import CHARACTERS, CLUES, COMMON_STORY, ENDINGS, PHASES, PLACES, TESTIMONIES, TIMELINE
from app.default_phases import COMMON_PHASES


def test_four_characters_with_one_culprit_and_distinct_voices():
    assert len(CHARACTERS) == 4 and [c["범인"] for c in CHARACTERS].count(True) == 1
    assert len({c["이름"] for c in CHARACTERS}) == 4
    for c in CHARACTERS:
        assert len(c["서사"]) == 2 and "[말투]" in c["서사"][0] and c["소개"] and c["캐릭터설명"]       # 말투 안내와 그 말투로 쓴 소개 멘트
        assert len(c["소개"]) <= 1000 and len(c["캐릭터설명"]) <= 1000 and len(c["비밀"]) <= 2000 and len(c["목표"]) <= 2000
        assert len(narrative.join([narrative.Part(None, t) for t in c["서사"]])) <= narrative.TOTAL_LIMIT


def test_each_voice_is_recognizable_in_the_self_introduction():
    intro = {c["이름"]: c["소개"] for c in CHARACTERS}
    assert intro["오태훈"].endswith("이상입니다.") and "습니다" in intro["오태훈"]            # 다나까
    assert "나 황칠성이다" in intro["황칠성"] and "재미없어" in intro["황칠성"]                 # 거친 반말
    assert "에요" in intro["한유진"]                                                          # 부드러운 해요체
    assert "여." in intro["정막례"] and "니께" in intro["정막례"]                              # 노인 말투


def test_story_fits_limits_and_every_clue_has_an_existing_place():
    assert len(COMMON_STORY) <= narrative.COMMON_TOTAL_LIMIT
    places = {name for name, _ in PLACES}
    assert len(places) == 4
    for place, name, shown, text in [*CLUES, *TESTIMONIES]:
        assert place in places and name and shown and text and len(name) <= 100 and len(shown) <= 100 and len(text) <= 5000
    assert len(CLUES) == 8 and len(TESTIMONIES) == 3
    for start, end, text in TIMELINE:
        assert start <= end and text


def test_flow_uses_registered_common_phases_and_two_endings_cover_every_vote():
    common = {name for name, *_ in COMMON_PHASES}
    for _, cards, _ in PHASES:
        for name, _ in cards:
            assert name in common, name
    assert [n for n, *_ in ENDINGS] == ["범인 검거", "검거 실패"]
    assert "한유진" in ENDINGS[0][2]
