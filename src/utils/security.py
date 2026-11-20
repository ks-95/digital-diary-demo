# src/utils/security.py
"""JWT and password hashing for Digital Diary. The signing key comes from JWT_SECRET_KEY in src/.env."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from utils.settings import settings

# sha256_crypt is stable across passlib/bcrypt versions on Windows
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)


def _secret() -> str:
    if not settings.JWT_SECRET_KEY or len(settings.JWT_SECRET_KEY) < 32:
        raise RuntimeError("JWT_SECRET_KEY missing or too short in src/.env (use 32+ random chars).")
    return settings.JWT_SECRET_KEY


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + (expires_delta or timedelta(hours=12))
    return jwt.encode(to_encode, _secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except JWTError:
        return None


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    token: Optional[str] = Query(None, description="Token for browser downloads (documents)"),
) -> dict:
    """Requires a valid JWT in 'Authorization: Bearer' header (or ?token= for file downloads)."""
    raw = creds.credentials if creds else token
    payload = decode_access_token(raw) if raw else None
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required or session expired.")
    return payload
