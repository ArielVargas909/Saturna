from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

_hasher = PasswordHash.recommended()  # argon2


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _hasher.verify(password, hashed)


def create_token(user_id: int, kind: str, minutes: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "type": kind, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def decode_token(token: str, kind: str) -> int | None:
    try:
        data = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if data.get("type") != kind:
        return None
    try:
        return int(data["sub"])
    except (KeyError, ValueError):
        return None
