import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.config import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    DEFAULT_ADMIN_USER,
    DEFAULT_ADMIN_PASS,
    DEFAULT_ADMIN_EMAIL,
    logger,
)
from app.database import get_db
from app.models import User

security = HTTPBearer(auto_error=False)

ADMIN_ROLES = ("ADMIN", "SUPER_ADMIN", "HR_MANAGER")


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with a unique cryptographic salt."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"{salt}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against the stored PBKDF2 hash using constant-time comparison."""
    if not hashed_password or "$" not in hashed_password:
        return False
    try:
        salt, key_hex = hashed_password.split("$", 1)
        computed = hashlib.pbkdf2_hmac(
            "sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), 100000
        )
        return hmac.compare_digest(computed.hex(), key_hex)
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


def get_token_from_request(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = None,
) -> Optional[str]:
    """Extract token from Authorization header or 'access_token' cookie."""
    if credentials and hasattr(credentials, "credentials"):
        return credentials.credentials
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        if cookie_token.startswith("Bearer "):
            return cookie_token[7:].strip()
        return cookie_token.strip()
    return None


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency to retrieve the authenticated user from JWT."""
    token = get_token_from_request(request, credentials)
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    payload = decode_token(token)
    if payload is None:
        raise credentials_exception

    user_code: str = payload.get("sub")
    if user_code is None:
        raise credentials_exception

    user = db.query(User).filter(User.user_code == user_code, User.is_active == True).first()
    if user is None:
        raise credentials_exception
    return user


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """FastAPI dependency to enforce Administrator / HR Manager privileges."""
    if current_user.role not in ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required (ADMIN, SUPER_ADMIN, or HR_MANAGER)",
        )
    return current_user


def seed_default_admin(db: Session):
    """Seed default superadmin account if no admin exists."""
    admin = db.query(User).filter(User.role.in_(ADMIN_ROLES)).first()
    if not admin:
        admin_user = User(
            user_code=DEFAULT_ADMIN_USER,
            full_name="System Administrator",
            email=DEFAULT_ADMIN_EMAIL,
            role="SUPER_ADMIN",
            password_hash=hash_password(DEFAULT_ADMIN_PASS),
            is_active=True,
        )
        db.add(admin_user)
        db.commit()
        logger.info(
            "Default SuperAdmin created: username='%s' (Please change default password immediately)",
            DEFAULT_ADMIN_USER,
        )
