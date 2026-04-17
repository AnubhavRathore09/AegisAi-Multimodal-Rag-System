from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas import AuthResponse, AuthUser, LoginRequest, SignupRequest
from app.services.auth import create_access_token, get_current_user_id, hash_password, verify_password
from app.services.memory import memory_store

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_payload(profile: dict) -> AuthUser:
    return AuthUser(
        id=str(profile.get("user_id", "")),
        name=str(profile.get("name", "User")),
        email=str(profile.get("email", "")),
        bot_name=str(profile.get("bot_name", "Aegis AI")),
    )


@router.post("/signup", response_model=AuthResponse)
async def signup(payload: SignupRequest) -> AuthResponse:
    existing = memory_store.get_user_by_email(payload.email)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    profile = memory_store.create_user(payload.name, payload.email, hash_password(payload.password))
    token = create_access_token(str(profile["user_id"]), str(profile["email"]))
    return AuthResponse(access_token=token, user=_user_payload(profile))


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest) -> AuthResponse:
    profile = memory_store.get_user_by_email(payload.email)
    if profile is None or not verify_password(payload.password, str(profile.get("password_hash", ""))):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token = create_access_token(str(profile["user_id"]), str(profile["email"]))
    return AuthResponse(access_token=token, user=_user_payload(profile))


@router.get("/me", response_model=AuthUser)
async def me(user_id: str = Depends(get_current_user_id)) -> AuthUser:
    profile = memory_store.get_user_by_id(user_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _user_payload(profile)
