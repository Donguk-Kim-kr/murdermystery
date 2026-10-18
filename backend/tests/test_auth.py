import uuid

import psycopg
import pytest

from app.auth import SESSION_LONG, SESSION_SHORT
from app.security import hash_token

PW = "correct-horse-battery"


@pytest.fixture
def db(test_dbname):
    with psycopg.connect(f"dbname={test_dbname}", autocommit=True) as conn:
        yield conn


@pytest.fixture
def user(client):
    uid = f"u{uuid.uuid4().hex[:10]}"
    res = client.post("/api/auth/signup", json={"아이디": uid, "패스워드": PW, "닉네임": "탐정"})
    assert res.status_code == 201
    return {"아이디": uid, **res.json()}


def login(client, user, **kw):
    body = {"아이디": user["아이디"], "패스워드": PW, "접속환경": "PC", **kw}
    return client.post("/api/auth/login", json=body)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_signup_returns_account_without_password(user):
    assert set(user) == {"번호", "아이디", "닉네임", "권한"}
    assert user["권한"] == "사용자"
    assert user["닉네임"] == "탐정"


def test_signup_stores_argon2_hash_not_plaintext(user, db):
    stored = db.execute('SELECT "패스워드", "상태" FROM "계정" WHERE "번호" = %s', (user["번호"],)).fetchone()
    assert stored[0].startswith("$argon2") and PW not in stored[0]
    assert stored[1] == "정상"


def test_signup_duplicate_id_conflicts(client, user):
    res = client.post("/api/auth/signup", json={"아이디": user["아이디"], "패스워드": PW, "닉네임": "다른사람"})
    assert res.status_code == 409


@pytest.mark.parametrize("patch", [
    {"패스워드": "short"},
    {"아이디": ""},
    {"아이디": "has space"},
    {"닉네임": ""},
])
def test_signup_validation(client, patch):
    body = {"아이디": f"u{uuid.uuid4().hex[:10]}", "패스워드": PW, "닉네임": "n", **patch}
    assert client.post("/api/auth/signup", json=body).status_code == 422


def test_login_me_roundtrip(client, user):
    res = login(client, user)
    assert res.status_code == 200
    body = res.json()
    me = client.get("/api/auth/me", headers=auth(body["토큰"]))
    assert me.status_code == 200 and me.json() == user


def test_token_is_stored_hashed(client, user, db):
    token = login(client, user).json()["토큰"]
    rows = db.execute('SELECT "토큰" FROM "로그인세션" WHERE "계정_번호" = %s', (user["번호"],)).fetchall()
    assert [r[0] for r in rows] == [hash_token(token)]
    assert token not in rows[0][0]


@pytest.mark.parametrize("auto,ttl", [(False, SESSION_SHORT), (True, SESSION_LONG)])
def test_session_lifetime_and_environment(client, user, db, auto, ttl):
    login(client, user, 자동로그인=auto, 접속환경="모바일")
    created, expires, env = db.execute(
        'SELECT "생성일시", "만료일시", "접속환경" FROM "로그인세션" WHERE "계정_번호" = %s', (user["번호"],)
    ).fetchone()
    assert expires - created == ttl and env == "모바일"


def test_login_tells_an_unknown_id_from_a_wrong_password(client, user):
    wrong = client.post("/api/auth/login", json={"아이디": user["아이디"], "패스워드": "x" * 10, "접속환경": "PC"})
    unknown = client.post("/api/auth/login", json={"아이디": "nobody-here", "패스워드": PW, "접속환경": "PC"})
    assert wrong.status_code == unknown.status_code == 401
    assert unknown.json()["detail"] == "아이디가 존재하지 않습니다"
    assert wrong.json()["detail"] == "패스워드가 올바르지 않습니다 (남은 시도 9회)"


def test_login_rejects_invalid_environment(client, user):
    assert login(client, user, 접속환경="콘솔").status_code == 422


@pytest.mark.parametrize("state", ["정지", "탈퇴"])
def test_login_denied_for_inactive_account(client, user, db, state):
    db.execute('UPDATE "계정" SET "상태" = %s WHERE "번호" = %s', (state, user["번호"]))
    assert login(client, user).status_code == 403


def test_existing_session_denied_after_account_suspended(client, user, db):
    token = login(client, user).json()["토큰"]
    db.execute('UPDATE "계정" SET "상태" = %s WHERE "번호" = %s', ("정지", user["번호"]))
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 401


def test_logout_revokes_only_that_session(client, user, db):
    t1 = login(client, user).json()["토큰"]
    t2 = login(client, user).json()["토큰"]
    assert client.post("/api/auth/logout", headers=auth(t1)).status_code == 204
    assert client.get("/api/auth/me", headers=auth(t1)).status_code == 401
    assert client.get("/api/auth/me", headers=auth(t2)).status_code == 200
    revoked = db.execute('SELECT count(*) FROM "로그인세션" WHERE "계정_번호" = %s AND "폐기일시" IS NOT NULL', (user["번호"],)).fetchone()
    assert revoked[0] == 1


def test_expired_session_denied(client, user, db):
    token = login(client, user).json()["토큰"]
    db.execute(
        'UPDATE "로그인세션" SET "생성일시" = CURRENT_TIMESTAMP - interval \'2 hours\', '
        '"만료일시" = CURRENT_TIMESTAMP - interval \'1 hour\' WHERE "토큰" = %s',
        (hash_token(token),),
    )
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 401


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer"}, {"Authorization": "Basic abc"},
                                     {"Authorization": "Bearer not-a-real-token"}])
def test_me_requires_valid_bearer_token(client, headers):
    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 401 and res.headers["www-authenticate"] == "Bearer"


def test_signup_ignores_role_sent_by_client(client):
    uid = f"u{uuid.uuid4().hex[:10]}"
    res = client.post("/api/auth/signup", json={"아이디": uid, "패스워드": PW, "닉네임": "n", "권한": "운영자"})
    assert res.status_code == 201 and res.json()["권한"] == "사용자"


@pytest.mark.parametrize("role", ["관리자", "운영자"])
def test_role_set_in_database_is_reported_on_login_and_me(client, user, db, role):
    db.execute('UPDATE "계정" SET "권한" = %s WHERE "번호" = %s', (role, user["번호"]))
    body = login(client, user).json()
    assert body["계정"]["권한"] == role
    assert client.get("/api/auth/me", headers=auth(body["토큰"])).json()["권한"] == role


def test_database_rejects_unknown_role(user, db):
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute('UPDATE "계정" SET "권한" = %s WHERE "번호" = %s', ("왕", user["번호"]))


def test_password_minimum_length_can_be_lowered_by_setting_for_testing(client, monkeypatch):
    from app.config import get_settings

    body = {"아이디": "shortpw", "패스워드": "a", "닉네임": "짧은"}
    res = client.post("/api/auth/signup", json=body)
    assert res.status_code == 422
    error = res.json()["detail"][0]
    assert error["type"] == "string_too_short" and error["ctx"]["min_length"] == 8 and error["loc"][-1] == "패스워드"
    monkeypatch.setenv("MM_PASSWORD_MIN_LENGTH", "1")
    get_settings.cache_clear()
    try:
        assert client.post("/api/auth/signup", json=body).status_code == 201
        assert client.post("/api/auth/signup", json={**body, "아이디": "emptypw", "패스워드": ""}).status_code == 422   # 0자는 낮춰도 안 된다
    finally:
        monkeypatch.delenv("MM_PASSWORD_MIN_LENGTH")
        get_settings.cache_clear()
    assert client.post("/api/auth/signup", json={**body, "아이디": "again"}).status_code == 422


# ---- 패스워드 입력 제한과 초기화 (사용자 결정 2026-10-18) -----------------------------------------------

@pytest.fixture
def clock():
    """로그인 제한의 시계를 손으로 움직인다."""
    from app import auth

    now = {"t": 1000.0}
    original = auth.guard.clock
    auth.guard.clock = lambda: now["t"]
    yield now
    auth.guard.clock = original


def wrong_login(client, user, password="x" * 10):
    return client.post("/api/auth/login", json={"아이디": user["아이디"], "패스워드": password, "접속환경": "PC"})


def test_ten_wrong_passwords_lock_the_id_for_five_minutes_even_for_the_right_password(client, user, clock):
    for n in range(9):
        res = wrong_login(client, user)
        assert res.status_code == 401 and res.json()["detail"] == f"패스워드가 올바르지 않습니다 (남은 시도 {9 - n}회)"
    tenth = wrong_login(client, user)
    assert tenth.status_code == 429 and "5분 뒤에 다시 시도" in tenth.json()["detail"] and tenth.headers["Retry-After"] == "300"
    clock["t"] += 120
    blocked = login(client, user)                                              # 맞는 패스워드도 막혀 있는 동안은 받지 않는다
    assert blocked.status_code == 429 and "3분 뒤에 다시 시도" in blocked.json()["detail"]
    clock["t"] += 181
    assert login(client, user).status_code == 200                              # 5분이 지나면 다시 입력할 수 있다


def test_a_successful_login_resets_the_failure_count(client, user, clock):
    for _ in range(9):
        wrong_login(client, user)
    assert login(client, user).status_code == 200
    assert wrong_login(client, user).json()["detail"].endswith("(남은 시도 9회)")


def test_after_the_lock_ends_counting_starts_over(client, user, clock):
    for _ in range(10):
        wrong_login(client, user)
    clock["t"] += 301
    assert wrong_login(client, user).json()["detail"].endswith("(남은 시도 9회)")


def test_locking_one_id_does_not_affect_another(client, user, clock):
    for _ in range(10):
        wrong_login(client, user)
    other = client.post("/api/auth/signup", json={"아이디": f"o{uuid.uuid4().hex[:10]}", "패스워드": PW, "닉네임": "다른"}).json()
    assert client.post("/api/auth/login", json={"아이디": other["아이디"], "패스워드": PW, "접속환경": "PC"}).status_code == 200


def test_unknown_ids_are_not_counted(client, clock):
    for _ in range(12):
        res = client.post("/api/auth/login", json={"아이디": "ghost-id", "패스워드": "x", "접속환경": "PC"})
        assert res.status_code == 401 and res.json()["detail"] == "아이디가 존재하지 않습니다"


def reset(client, user, **over):
    body = {"아이디": user["아이디"], "닉네임": "탐정", "새_패스워드": "brand-new-pw", **over}
    return client.post("/api/auth/reset-password", json=body)


def test_reset_needs_both_id_and_nickname_and_changes_the_password(client, user, clock):
    assert reset(client, user, 닉네임="다른닉").json()["detail"] == "닉네임이 맞지 않습니다 (남은 시도 9회)"
    assert reset(client, user, 아이디="ghost-id").json()["detail"] == "아이디가 존재하지 않습니다"
    assert login(client, user).status_code == 200                              # 아직 옛 패스워드
    assert reset(client, user).status_code == 204
    assert login(client, user).status_code == 401                              # 옛 패스워드는 더 이상 되지 않는다
    assert login(client, user, 패스워드="brand-new-pw").status_code == 200


def test_reset_logs_out_every_existing_session_and_shows_no_notice(client, user, db, clock):
    old = login(client, user).json()["토큰"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {old}"}).status_code == 200
    assert reset(client, user).status_code == 204
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {old}"}).status_code == 401
    new = login(client, user, 패스워드="brand-new-pw")
    assert new.status_code == 200 and set(new.json()) == {"토큰", "만료일시", "계정"}   # 로그인 응답에 알림이 따로 없다


def test_reset_failures_share_the_login_limit(client, user, clock):
    for _ in range(5):
        reset(client, user, 닉네임="틀림")
    for _ in range(4):
        wrong_login(client, user)
    last = reset(client, user, 닉네임="틀림")                                   # 합쳐서 10번째
    assert last.status_code == 429
    assert login(client, user).status_code == 429 and reset(client, user).status_code == 429


def test_reset_applies_the_password_length_rule_and_blocks_inactive_accounts(client, user, db, clock):
    short = reset(client, user, 새_패스워드="짧")
    assert short.status_code == 422 and short.json()["detail"][0]["type"] == "string_too_short"
    db.execute('UPDATE "계정" SET "상태" = %s WHERE "번호" = %s', ("정지", user["번호"]))
    res = reset(client, user)
    assert res.status_code == 403 and "바꿀 수 없는 계정" in res.json()["detail"]
