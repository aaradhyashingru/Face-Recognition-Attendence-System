from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth import verify_password, create_access_token
from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(login_data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Authenticate administrator or user and issue JWT."""
    user = (
        db.query(User)
        .filter(
            (User.user_code == login_data.username) | (User.email == login_data.username),
            User.is_active == True,
        )
        .first()
    )

    if not user or not user.password_hash or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(data={"sub": user.user_code, "role": user.role})

    # Set secure HTTP-only cookie for web views
    response.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        samesite="lax",
        max_age=86400,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_code=user.user_code,
        full_name=user.full_name,
        role=user.role,
    )


@router.post("/logout")
def logout(response: Response):
    """Clear session cookie."""
    response.delete_cookie("access_token")
    return {"message": "Successfully logged out"}
