from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.logging import logger

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return {"username": username}
    except JWTError:
        return None

def authenticate_user(username: str, password: str) -> bool:
    """
    Authenticate admin user
    
    Authentication priority:
    1. If ADMIN_PASSWORD_HASH is set, verify with hash (production)
    2. If ADMIN_PASSWORD_HASH is empty, verify with plain text password (development)
    """
    if username == settings.ADMIN_USERNAME:
        # 1. If hashed password is set, verify with hash (production)
        hash_value = getattr(settings, 'ADMIN_PASSWORD_HASH', '')
        if hash_value and hash_value.strip():  # If not empty string
            try:
                return verify_password(password, hash_value)
            except Exception as e:
                logger.warning("Hash verification failed")
                return False
        
        # 2. If hash is empty or missing, verify with plain text password (development)
        plain_password = getattr(settings, 'ADMIN_PASSWORD', '')
        if plain_password:
            if password == plain_password:
                logger.info("Using development authentication mode")
                return True
    
    return False