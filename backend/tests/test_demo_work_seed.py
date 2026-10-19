"""샘플 작품의 제작 계정 패스워드(MM_SAMPLE_MAKER_PASSWORD)를 정하면 그 패스워드로 로그인할 수 있다(app/demo_work.py)."""
from app.demo_work import MAKER_ID, MAKER_NICKNAME, fixed_password, seed


def _login(client, password: str):
    return client.post("/api/auth/login", json={"아이디": MAKER_ID, "패스워드": password, "접속환경": "PC"})


def test_fixed_password_is_empty_unless_the_variable_is_set(monkeypatch):
    monkeypatch.delenv("MM_SAMPLE_MAKER_PASSWORD", raising=False)
    assert fixed_password() == ""
    monkeypatch.setenv("MM_SAMPLE_MAKER_PASSWORD", "  sample-pass-1 ")
    assert fixed_password() == "sample-pass-1"


def test_an_existing_maker_account_gets_the_fixed_password(client, monkeypatch):
    """계정이 이미 있는 경우(켤 때마다 시드가 도는 도커): 고정 패스워드로 맞춘다. 작품을 다시 만들지는 않는다."""
    monkeypatch.setenv("MM_SAMPLE_MAKER_PASSWORD", "sample-pass-1")
    made = client.post("/api/auth/signup", json={"아이디": MAKER_ID, "패스워드": "random-initial-pass", "닉네임": MAKER_NICKNAME})
    assert made.status_code == 201
    assert _login(client, "sample-pass-1").status_code == 401           # 아직 처음 패스워드이다
    assert seed(client) == "이미 있음"
    assert _login(client, "sample-pass-1").status_code == 200
    assert _login(client, "random-initial-pass").status_code == 401


def test_without_the_variable_an_existing_maker_account_is_left_alone(client, monkeypatch):
    monkeypatch.delenv("MM_SAMPLE_MAKER_PASSWORD", raising=False)
    assert seed(client) == "이미 있음"
    assert _login(client, "sample-pass-1").status_code == 200           # 앞 시험에서 맞춘 패스워드가 그대로이다
