"""서사 부분 나누기 (docs/ENGINE_DESIGN.md 1-4-6)."""
import pytest

from app import narrative as n
from app.narrative import NarrativeError, Part


def test_text_without_markers_is_one_part_without_id():
    assert n.split("옛 서사\n두 번째 줄") == [Part(None, "옛 서사\n두 번째 줄")]
    assert n.split("") == [] and n.split("  \n ") == []


def test_split_reads_markers():
    raw = "@@MMPART:k3x9ab@@\n첫째\n둘째 줄\n@@MMPART:q8m2zt@@\n셋째"
    assert n.split(raw) == [Part("k3x9ab", "첫째\n둘째 줄"), Part("q8m2zt", "셋째")]


def test_split_is_tolerant_about_spaces_newlines_and_leading_text():
    raw = "앞글\r\n  @@MMPART:aaaaaa@@  \r\n\r\n본문\r\n\r\n@@MMPART:bbbbbb@@\n둘째\n"
    assert n.split(raw) == [Part(None, "앞글"), Part("aaaaaa", "본문"), Part("bbbbbb", "둘째")]


def test_marker_must_be_a_whole_line_to_count():
    raw = "@@MMPART:aaaaaa@@\n문장 중간의 @@MMPART:bbbbbb@@ 은 표기가 아니다"
    assert n.split(raw) == [Part("aaaaaa", "문장 중간의 @@MMPART:bbbbbb@@ 은 표기가 아니다")]
    assert n.split("@@MMPART:ABCDEF@@\n대문자는 표기가 아니다") == [Part(None, "@@MMPART:ABCDEF@@\n대문자는 표기가 아니다")]


def test_join_adds_ids_keeps_existing_and_round_trips():
    raw = n.join([Part("k3x9ab", "첫째"), Part(None, "둘째\n줄")])
    assert raw.startswith("@@MMPART:k3x9ab@@\n첫째\n@@MMPART:")
    parts = n.split(raw)
    assert [p.text for p in parts] == ["첫째", "둘째\n줄"]
    assert parts[0].id == "k3x9ab" and parts[1].id and parts[1].id != "k3x9ab" and len(parts[1].id) == 6
    assert n.join(parts) == raw                                    # 다시 합쳐도 같다(ID 유지)


def test_join_does_not_change_the_given_parts_and_ids_are_unique():
    given = [Part(None, str(i)) for i in range(5)]
    raw = n.join(given)
    assert all(p.id is None for p in given)
    ids = [p.id for p in n.split(raw)]
    assert len(set(ids)) == 5


def test_join_trims_blank_lines_and_normalizes_newlines():
    raw = n.join([Part("aaaaaa", "\n\n본문\r\n줄\n\n")])
    assert raw == "@@MMPART:aaaaaa@@\n본문\n줄"


@pytest.mark.parametrize("parts, message", [
    ([Part(None, "본문 @@MMPART:zzzzzz@@ 안")], "예약된 표기"),
    ([Part(None, "@@MMPART:")], "예약된 표기"),
    ([Part(None, "   \n ")], "비어 있습니다"),
    ([Part("aaaaaa", "가"), Part("aaaaaa", "나")], "겹칩니다"),
    ([Part("AB", "가")], "올바르지 않습니다"),
    ([Part(None, "가")] * 6, "5개까지"),
    ([Part(None, "가" * 10001)], "너무 깁니다"),
    ([Part(None, "가" * 5001), Part(None, "나")], "너무 깁니다"),
])
def test_join_rejects(parts, message):
    with pytest.raises(NarrativeError) as err:
        n.join(parts)
    assert message in str(err.value)


@pytest.mark.parametrize("count, limit", [(1, 10000), (2, 5000), (3, 3333), (4, 2500), (5, 2000)])
def test_part_limit_halves_as_parts_are_added(count, limit):
    assert n.part_limit(count) == limit
    n.join([Part(None, "가" * limit) for _ in range(count)])           # 딱 제한만큼은 저장된다
    with pytest.raises(NarrativeError):
        n.join([Part(None, "가" * (limit + 1))] + [Part(None, "가") for _ in range(count - 1)])


def test_check_fits_lists_parts_that_would_exceed_new_limit():
    parts = [Part(None, "가" * 8000), Part(None, "나" * 100)]
    assert n.check_fits(parts) == [1]                                  # 서사를 2개로 나누면 1번은 5000자를 넘는다
    assert n.check_fits(parts[:1]) == []


def test_numbered_picks_parts_in_order_and_skips_missing():
    raw = n.join([Part(None, "하나"), Part(None, "둘"), Part(None, "셋")])
    assert n.numbered(raw, [1]) == "하나"
    assert n.numbered(raw, [3, 1]) == "하나\n\n셋"
    assert n.numbered(raw, [2, 2, 9, 0]) == "둘"
    assert n.numbered("옛 서사", [1]) == "옛 서사"
    assert n.numbered("옛 서사", [2]) == ""
