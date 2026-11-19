
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
)
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    UserResponse,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    data: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    email = str(data.email).strip().lower()

    existing_user = await db.execute(
        select(User).where(User.email == email)
    )

    if existing_user.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Email already registered",
        )

    user = User(
        full_name=data.full_name.strip(),
        email=email,
        password_hash=hash_password(data.password),
    )

    db.add(user)

    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Email already registered",
        )

    return user


@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login(
    data: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    email = str(data.email).strip().lower()

    result = await db.execute(
        select(User).where(User.email == email)
    )

    user = result.scalar_one_or_none()

    if not user or not verify_password(
        data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    access_token = create_access_token(str(user.id))

    return TokenResponse(access_token=access_token)


@router.get(
    "/me",
    response_model=UserResponse,
)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    return current_user
