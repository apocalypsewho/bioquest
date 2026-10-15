"""Minimal, dependency-free auth: PBKDF2 password hashes + HMAC-signed bearer tokens.

Good enough for an MVP; swap for an identity provider (OIDC) in production.
"""
import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

_ITER = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"pbkdf2${_ITER}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, it, salt, digest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(dk.hex(), digest)
    except ValueError:
        return False


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(user_id: int) -> str:
    s = get_settings()
    payload = _b64(json.dumps({"uid": user_id, "exp": int(time.time()) + s.token_ttl_hours * 3600}).encode())
    sig = _b64(hmac.new(s.secret_key.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def decode_token(token: str) -> int | None:
    s = get_settings()
    try:
        payload, sig = token.split(".")
    except ValueError:
        return None
    expected = _b64(hmac.new(s.secret_key.encode(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    data = json.loads(_unb64(payload))
    if data.get("exp", 0) < time.time():
        return None
    return int(data["uid"])


def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    token = authorization.removeprefix("Bearer ").strip()
    uid = decode_token(token) if token else None
    user = db.get(User, uid) if uid else None
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


def optional_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User | None:
    token = authorization.removeprefix("Bearer ").strip()
    uid = decode_token(token) if token else None
    return db.get(User, uid) if uid else None


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    return user
