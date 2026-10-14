"""비밀번호 해시와 세션 토큰.

* 비밀번호: Argon2 (pwdlib 기본값). 솔트가 해시에 포함되어 있어 조회용으로는 쓸 수 없다.
* 세션 토큰: 추측 불가능한 무작위 값이므로 SHA-256 으로 저장해도 안전하다. DB 에는 해시만 둔다.
"""
import hashlib
import secrets

from pwdlib import PasswordHash

_hasher = PasswordHash.recommended()
# 존재하지 않는 아이디로 로그인 시도할 때도 해시 검증 시간을 쓰도록 하는 더미 해시 (계정 존재 여부 노출 방지).
DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _hasher.verify(password, hashed)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
