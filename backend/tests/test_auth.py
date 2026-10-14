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


def test_login_wrong_password_and_unknown_id_look_the_same(client, user):
    wrong = client.post("/api/auth/login", json={"아이디": user["아이디"], "패스워드": "x" * 10, "접속환경": "PC"})
    unknown = client.post("/api/auth/login", json={"아이디": "nobody-here", "패스워드": PW, "접속환경": "PC"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


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
