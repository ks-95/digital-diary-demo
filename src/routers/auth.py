# src/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from utils.db import get_db
from utils.security import get_password_hash, verify_password, create_access_token, get_current_user
from models.user import User
from schemas.dtos import RegisterRequest, LoginRequest, Token

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])


@auth_router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(reg: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new police officer account using mobile number."""
    stmt = select(User).where(User.mobile_number == reg.mobile_number)
    existing = await db.scalar(stmt)
    if existing:
        raise HTTPException(status_code=400, detail="Mobile number already registered.")

    hashed = get_password_hash(reg.password)
    new_user = User(
        mobile_number=reg.mobile_number,
        hashed_password=hashed,
        name=reg.name,
        station=reg.station,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    token = create_access_token({
        "sub": str(new_user.id),
        "mobile": new_user.mobile_number,
        "name": new_user.name,
        "station": new_user.station,
    })
    return Token(
        access_token=token,
        user_id=str(new_user.id),
        mobile_number=new_user.mobile_number,
        name=new_user.name,
        station=new_user.station,
    )


@auth_router.post("/login", response_model=Token)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with mobile number and password."""
    stmt = select(User).where(User.mobile_number == req.mobile_number)
    user = await db.scalar(stmt)
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid mobile number or password.")

    token = create_access_token({
        "sub": str(user.id),
        "mobile": user.mobile_number,
        "name": user.name,
        "station": user.station,
    })
    return Token(
        access_token=token,
        user_id=str(user.id),
        mobile_number=user.mobile_number,
        name=user.name,
        station=user.station,
    )


@auth_router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Return info about the logged-in officer."""
    return {"user_id": user.get("sub"), "mobile_number": user.get("mobile"), "name": user.get("name"), "station": user.get("station")}

