"""진행단계 스크립트가 정하는 제작 화면: 설정정의·조건정의 (app/declare.py)."""
import pytest

from app.cards import known_names
from app.declare import declarations
from app.default_phases import COMMON_PHASES
from app.script import ScriptError

SOURCE = '''
def 설정정의(카드):
    return [숫자칸("횟수", "조사 횟수", 3, 최소=1), 선택칸("동률", "동률", [["구속없음", "결과 없음"], "재투표"]), 켜짐칸("허용", "허용"), 여러선택칸("대상", "대상", ["인물", "장소"], ["인물"])]

def 조건정의(카드):
    return [조건항목("동률이다", "len(최다득표('최종 투표')) > 1"), 조건항목("이 인물이다", "결과_인물('최종 투표').순서 == {인물}", [인물칸("인물", "인물")])]

def 실행(카드):
    통과
'''


def test_declared_settings_and_conditions_are_collected_without_running_the_game():
    got = declarations(SOURCE, known_names())
    assert [s["키"] for s in got["설정"]] == ["횟수", "동률", "허용", "대상"]
    assert got["설정"][0] == {"키": "횟수", "이름": "조사 횟수", "종류": "숫자", "기본": 3, "최소": 1, "설명": ""}
    assert got["설정"][1]["선택"] == [["구속없음", "결과 없음"], ["재투표", "재투표"]] and got["설정"][1]["기본"] == "구속없음"
    assert got["설정"][3]["기본"] == ["인물"]
    assert [c["이름"] for c in got["조건"]] == ["동률이다", "이 인물이다"] and got["조건"][1]["인자"][0]["종류"] == "인물"


def test_script_without_declarations_gives_none():
    assert declarations("def 실행(카드):\n    통과", known_names()) is None


@pytest.mark.parametrize("body, message", [
    ('return [숫자칸("횟수", "x", 0, 최소=1)]', "기본값"),
    ('return [숫자칸("a", "x", 1), 숫자칸("a", "y", 1)]', "겹칩니다"),
    ('return 3', "목록"),
    ('return [선택칸("a", "x", [])]', "선택지"),
    ('return [{"키": "a"}]', "칸"),
    ('return [켜짐칸("a:b", "x")]', "키"),
])
def test_bad_settings_are_refused(body, message):
    with pytest.raises(ScriptError, match=message):
        declarations(f"def 설정정의(카드):\n    {body}", known_names())


@pytest.mark.parametrize("body, message", [
    ('return [조건항목("a", "{없는} == 1")]', "인자"),
    ('return [조건항목("a", "1"), 조건항목("a", "2")]', "겹치지"),
    ('return [조건항목("a", "{@없는설정} == 1")]', "설정 칸"),
])
def test_bad_conditions_are_refused(body, message):
    with pytest.raises(ScriptError, match=message):
        declarations(f"def 조건정의(카드):\n    {body}", known_names())


def test_declaration_functions_cannot_touch_the_game():
    with pytest.raises(ScriptError):
        declarations("def 설정정의(카드):\n    return [숫자칸(카드.이름, 'x', 1)]", known_names())


def test_every_default_phase_declares_valid_settings_and_conditions():
    from app.script import compile_expression
    import re

    for name, _, source, _s in COMMON_PHASES:
        got = declarations(source, known_names())
        for cond in (got or {"조건": []})["조건"]:
            expression = re.sub(r"\{[^{}]+\}", "0", cond["식"])
            compile_expression(expression, known_names())       # 자리표시자를 값으로 바꾸면 올바른 식이다


def test_script_check_and_library_report_a_broken_declaration(client, headers):
    bad = "def 설정정의(카드):\n    return [숫자칸('a', 'x', 0, 최소=1)]"
    res = client.post("/api/scripts/check", headers=headers, json={"스크립트": bad})
    assert res.json()["정상"] is False and "기본값" in res.json()["오류"]
    saved = client.post("/api/library/phases", headers=headers, json={"이름": "내 단계", "규칙": {"스크립트": bad}})
    assert saved.status_code == 422 and "설정정의" in saved.json()["detail"]
    good = client.post("/api/library/phases", headers=headers, json={"이름": "내 단계", "규칙": {"스크립트": SOURCE}})
    assert good.status_code == 201, good.text


def test_work_bundle_carries_the_declared_settings_and_conditions(client, headers):
    work = client.post("/api/works", headers=headers, json={"제목": "작품"}).json()["번호"]
    lib = client.post("/api/library/phases", headers=headers, json={"이름": "내 단계", "규칙": {"스크립트": SOURCE}}).json()
    slot = client.post(f"/api/works/{work}/content/phases", headers=headers, json={"진행시간": 10}).json()["순서"]
    res = client.post(f"/api/works/{work}/content/phase-steps", headers=headers, json={"진행순서_순서": slot, "진행단계_번호": lib["번호"]})
    assert res.status_code == 201, res.text
    ref = client.get(f"/api/works/{work}/content", headers=headers).json()["library"]["phases"][str(lib["번호"])]
    assert [s["키"] for s in ref["설정정의"]] == ["횟수", "동률", "허용", "대상"] and ref["사용설정"] == ["횟수", "동률", "허용", "대상"]
    assert [c["이름"] for c in ref["조건정의"]] == ["동률이다", "이 인물이다"]
