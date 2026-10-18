"""한국어 조사(을/를, 이/가, 은/는, 과/와, 으로/로 …)를 앞 낱말의 받침에 맞게 붙인다 (사용자 2026-10-18: "을(를)" 같은 표기를 없앤다).

화면 글, 오류 메시지, 스크립트의 알림이 모두 이것을 쓴다(프런트엔드의 `src/josa.ts` 와 같은 규칙이다).
낱말 끝의 따옴표·괄호·점 같은 기호는 건너뛰고 마지막 글자로 판단한다. 한글은 받침을 보고, 숫자와 영어 글자는 읽는 소리로 본다
(예: 1은 "일", 3은 "삼", L은 "엘" 이라 받침이 있고, 2는 "이", C는 "씨" 라 받침이 없다).
"""
PAIRS = {
    "을/를": ("을", "를"), "이/가": ("이", "가"), "은/는": ("은", "는"), "과/와": ("과", "와"),
    "으로/로": ("으로", "로"), "이나/나": ("이나", "나"), "이라/라": ("이라", "라"), "이랑/랑": ("이랑", "랑"), "아/야": ("아", "야"),
}
_DIGIT_FINAL = {"0": True, "1": True, "2": False, "3": True, "4": False, "5": False, "6": True, "7": True, "8": True, "9": False}   # 영 일 이 삼 사 오 육 칠 팔 구
_LATIN_FINAL = {"L": True, "M": True, "N": True, "R": True}        # 엘 엠 엔 알 만 받침이 있다(나머지 글자 이름은 모음으로 끝난다)
_LIEUL = 8                                                       # 한글 받침 ㄹ 의 번호


def _last_sound(word: str) -> tuple[bool, bool] | None:
    """(받침이 있는가, 받침이 ㄹ 인가). 판단할 글자가 없으면 None."""
    for ch in reversed(word):
        if "가" <= ch <= "힣":
            final = (ord(ch) - 0xAC00) % 28
            return final != 0, final == _LIEUL
        if ch in _DIGIT_FINAL:
            return _DIGIT_FINAL[ch], ch in "178"
        if ch.upper() in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" and ch.isascii():
            has = _LATIN_FINAL.get(ch.upper(), False)
            return has, ch.upper() == "L" or ch.upper() == "R"
    return None


def particle(word: str, pair: str) -> str:
    """`pair`("을/를" 등)에서 낱말에 맞는 쪽."""
    if pair not in PAIRS:
        raise ValueError(f"알 수 없는 조사입니다: {pair}")
    with_final, without = PAIRS[pair]
    sound = _last_sound(str(word))
    if sound is None:                       # 판단할 글자가 없으면 받침이 없는 쪽(가장 흔한 모양)
        return without
    has_final, is_lieul = sound
    if pair == "으로/로":
        return without if (not has_final or is_lieul) else with_final
    return with_final if has_final else without


def attach(word: str, pair: str) -> str:
    """낱말 뒤에 알맞은 조사를 붙여 돌려준다. 예: attach("커터칼", "을/를") → "커터칼을", attach("서랍", "이/가") → "서랍이"."""
    return f"{word}{particle(word, pair)}"


def quoted(word: str, pair: str) -> str:
    """작은따옴표로 감싼 낱말에 조사를 붙인다. 예: quoted("커터칼", "을/를") → "'커터칼'을"."""
    return attach(f"'{word}'", pair)
