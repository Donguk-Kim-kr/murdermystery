"""진행단계 스크립트 검사 API (편집기용)."""


def check(client, headers, source):
    res = client.post("/api/scripts/check", headers=headers, json={"스크립트": source})
    assert res.status_code == 200, res.text
    return res.json()


def test_valid_script_reports_its_functions(client, headers):
    result = check(client, headers, "def 실행(카드):\n    모두.보이기(글('안녕'))\n\ndef 진행조건(카드):\n    return 통과")
    assert result == {"정상": True, "오류": None, "줄": None, "함수": ["실행", "진행조건"]}


def test_empty_script_is_fine(client, headers):
    assert check(client, headers, "   \n")["정상"] is True


def test_errors_carry_message_and_line(client, headers):
    syntax = check(client, headers, "def 실행(카드):\n    x = (")
    assert syntax["정상"] is False and "문법 오류" in syntax["오류"] and syntax["줄"] == 2
    unknown = check(client, headers, "def 실행(카드):\n    몰라()")
    assert unknown["정상"] is False and "알 수 없는 이름" in unknown["오류"] and unknown["줄"] == 2
    banned = check(client, headers, "import os\n")
    assert banned["정상"] is False and banned["줄"] == 1


def test_checking_never_runs_the_script(client, headers):
    # 끝나지 않는 반복도 검사만 하므로 바로 돌려준다
    assert check(client, headers, "def 실행(카드):\n    while True:\n        pass")["정상"] is True


def test_requires_login_and_limits_size(client, headers):
    assert client.post("/api/scripts/check", json={"스크립트": "x"}).status_code == 401
    assert client.post("/api/scripts/check", headers=headers, json={"스크립트": "가" * 50001}).status_code == 422


def test_reference_lists_callable_names(client, headers):
    ref = client.get("/api/scripts/reference", headers=headers).json()
    assert "글" in ref["함수"] and "기다리기" in ref["함수"] and "통과" in ref["상수"] and "len" in ref["기본_함수"]
