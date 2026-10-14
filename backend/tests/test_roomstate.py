"""대기실 메모리 상태와 입장코드 시도 제한 (순수 로직, DB 불필요)."""
import pytest

from app.roomstate import JoinLimiter, RoomError, RoomRegistry


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def reg(clock):
    return RoomRegistry(member_timeout=20, clock=clock)


def test_host_opens_room_and_is_the_first_member(reg):
    room = reg.open_room(1, "ABC234", host_id=10, nickname="방장", playing=True)
    assert room.host_id == 10 and list(room.members) == [10] and room.player_count() == 1
    assert reg.room_of(10) is room


def test_observer_host_is_not_counted_as_player(reg):
    room = reg.open_room(1, "ABC234", 10, "방장", playing=False)
    assert room.player_count() == 0
    reg.join(1, 11, "가", capacity=1)  # 방장이 빠져 있으므로 1명 정원에 한 명이 들어올 수 있다
    assert room.player_count() == 1


def test_capacity_counts_only_players(reg):
    reg.open_room(1, "ABC234", 10, "방장", playing=True)
    reg.join(1, 11, "가", capacity=2)
    with pytest.raises(RoomError) as e:
        reg.join(1, 12, "나", capacity=2)
    assert e.value.code == "full"


def test_one_room_at_a_time(reg):
    reg.open_room(1, "AAA222", 10, "방장1", True)
    reg.open_room(2, "BBB222", 20, "방장2", True)
    reg.join(1, 11, "가", capacity=5)
    with pytest.raises(RoomError) as e:
        reg.join(2, 11, "가", capacity=5)
    assert e.value.code == "in_other_room"
    reg.leave(11)
    reg.join(2, 11, "가", capacity=5)  # 나간 뒤에는 다른 방에 들어갈 수 있다
    with pytest.raises(RoomError):
        reg.open_room(3, "CCC222", 11, "가", True)  # 다른 방에 있는 사람은 방을 만들 수 없다


def test_joining_the_same_room_again_is_harmless(reg):
    reg.open_room(1, "AAA222", 10, "방장", True)
    reg.join(1, 11, "가", capacity=5)
    room = reg.join(1, 11, "가", capacity=5)
    assert len(room.members) == 2


def test_member_is_dropped_when_polling_stops_but_host_stays(reg, clock):
    room = reg.open_room(1, "AAA222", 10, "방장", True)
    reg.join(1, 11, "가", capacity=5)
    clock.now += 21
    assert reg.get(1) is room
    assert list(room.members) == [10]                    # 입장자는 빠지고 방장은 남는다
    assert reg.room_of(11) is None                       # 다른 방에 들어갈 수 있게 풀린다


def test_touch_keeps_member_alive(reg, clock):
    reg.open_room(1, "AAA222", 10, "방장", True)
    reg.join(1, 11, "가", capacity=5)
    for _ in range(5):
        clock.now += 15
        reg.touch(11)
    assert 11 in reg.get(1).members


def test_remove_room_frees_everyone(reg):
    reg.open_room(1, "AAA222", 10, "방장", True)
    reg.join(1, 11, "가", capacity=5)
    reg.remove_room(1)
    assert reg.get(1) is None and reg.room_of(10) is None and reg.room_of(11) is None


def test_set_playing_respects_capacity(reg):
    reg.open_room(1, "AAA222", 10, "방장", playing=False)
    reg.join(1, 11, "가", capacity=1)
    with pytest.raises(RoomError):
        reg.set_playing(1, 10, True, capacity=1)
    reg.set_playing(1, 10, False, capacity=1)  # 이미 불참이면 그대로


def test_join_limiter_blocks_and_recovers(clock):
    lim = JoinLimiter(limit=3, window=60, clock=clock)
    for _ in range(3):
        assert not lim.blocked(1)
        lim.record_failure(1)
    assert lim.blocked(1) and not lim.blocked(2)  # 계정별로 센다
    clock.now += 61
    assert not lim.blocked(1)                     # 기간이 지나면 풀린다


def test_join_limiter_reset_on_success(clock):
    lim = JoinLimiter(limit=2, window=60, clock=clock)
    lim.record_failure(1)
    lim.record_failure(1)
    lim.reset(1)
    assert not lim.blocked(1)
