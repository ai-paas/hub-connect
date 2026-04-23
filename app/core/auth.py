from fastapi import Depends, HTTPException, status

from app.api.auth import oauth2_scheme
from app.services.auth_service import verify_token


async def get_current_user(token: str = Depends(oauth2_scheme)):
    user_data = verify_token(token)
    
    if user_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user_data