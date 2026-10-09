import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher

from app.core.config import get_settings

settings = get_settings()

# Default parameters conform to OWASP Argon2id recommendations
ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(hashed_password: str, plain_password: str) -> bool:
    try:
        return ph.verify(hashed_password, plain_password)
    except Exception:
        return False

def hash_refresh_token(token: str) -> str:
    """Creates a SHA-256 hash of the refresh token for DB storage."""
    return hashlib.sha256(token.encode()).hexdigest()

def generate_refresh_token() -> str:
    """Generates an opaque, cryptographically random string."""
    return secrets.token_urlsafe(32)

def create_access_token(user_id: str, role: str, jti: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES)
    to_encode = {
        "sub": str(user_id),
        "role": role,
        "jti": jti,
        "exp": expire,
        "iat": datetime.now(UTC)
    }
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm="HS256")
    return encoded_jwt

def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.PyJWTError:
        return None
