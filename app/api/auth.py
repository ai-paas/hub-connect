from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.auth_service import authenticate_user, create_access_token

router = APIRouter()

# OAuth2 Password Flow for Swagger UI
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


class Token(BaseModel):
    access_token: str = Field(..., description="발급된 JWT 액세스 토큰입니다.")
    token_type: str = Field(..., description="토큰 타입입니다. 항상 `bearer`입니다.")

@router.post(
    "/login",
    response_model=Token,
    summary="로그인",
    description=(
        "관리자 계정으로 로그인하여 액세스 토큰을 발급합니다.\n\n"
        "### 입력 필드\n"
        "| 필드 | 위치 | 필수 | 설명 | 예시 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| username | form-data | Y | 관리자 계정 아이디입니다. | admin |\n"
        "| password | form-data | Y | 관리자 계정 비밀번호입니다. | admin-password |\n\n"
        "### 응답 필드\n"
        "| 필드 | 설명 |\n"
        "| --- | --- |\n"
        "| access_token | 발급된 JWT 액세스 토큰입니다. |\n"
        "| token_type | 토큰 타입입니다. 항상 `bearer`입니다. |"
    ),
    responses={
        200: {
            "description": "로그인에 성공하여 토큰을 발급했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer",
                    }
                }
            },
        },
        401: {
            "description": "아이디 또는 비밀번호가 올바르지 않습니다.",
            "content": {
                "application/json": {
                    "example": {"detail": "Incorrect username or password"}
                }
            },
        },
        422: {
            "description": "로그인 요청 값 검증에 실패했습니다.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {
                                "type": "missing",
                                "loc": ["body", "username"],
                                "msg": "Field required",
                            }
                        ]
                    }
                }
            },
        },
    },
)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    if not authenticate_user(form_data.username, form_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": form_data.username}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}
