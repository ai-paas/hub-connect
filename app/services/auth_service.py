from datetime import datetime, timedelta
from typing import Optional, Union
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings

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
    관리자 사용자 인증
    
    인증 우선순위:
    1. ADMIN_PASSWORD_HASH가 설정되어 있으면 해시로 검증 (프로덕션)
    2. ADMIN_PASSWORD_HASH가 비어있으면 평문 비밀번호로 검증 (개발용)
    """
    if username == settings.ADMIN_USERNAME:
        # 1. 해시된 비밀번호가 설정되어 있으면 해시로 검증 (프로덕션)
        hash_value = getattr(settings, 'ADMIN_PASSWORD_HASH', '')
        if hash_value and hash_value.strip():  # 빈 문자열이 아닌 경우
            try:
                return verify_password(password, hash_value)
            except Exception as e:
                print(f"Hash verification failed: {e}")
                return False
        
        # 2. 해시가 없거나 비어있으면 평문 비밀번호로 검증 (개발용)
        plain_password = getattr(settings, 'ADMIN_PASSWORD', '')
        if plain_password:
            if password == plain_password:
                print("INFO: Using plain text password authentication (development mode)")
                return True
    
    return False