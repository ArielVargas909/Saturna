from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import DB, CurrentUser
from app.core.phone import normalize_optional
from app.core.ratelimit import check_rate
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import Tenant, User
from app.schemas import LoginIn, RefreshIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _tokens(user_id: int) -> TokenOut:
    return TokenOut(
        access_token=create_token(user_id, "access", settings.access_minutes),
        refresh_token=create_token(user_id, "refresh", settings.refresh_days * 24 * 60),
    )


@router.post("/register", response_model=TokenOut, status_code=201)
def register(data: RegisterIn, db: DB, request: Request):
    check_rate(f"register:{request.client.host if request.client else '-'}", 10, 3600)
    email = data.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "Ese correo ya está registrado")
    tenant = Tenant(name=data.tenant_name, address=data.address, zone=data.zone, plan="free")
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        name=data.name,
        email=email,
        password_hash=hash_password(data.password),
        role="owner",
        phone=normalize_optional(data.phone),
    )
    db.add(user)
    db.commit()
    return _tokens(user.id)


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: DB, request: Request):
    check_rate(f"login:{request.client.host if request.client else '-'}", 20, 60)
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user is None or not user.active or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Correo o contraseña incorrectos")
    return _tokens(user.id)


@router.post("/refresh", response_model=TokenOut)
def refresh(data: RefreshIn, db: DB):
    uid = decode_token(data.refresh_token, "refresh")
    user = db.get(User, uid) if uid else None
    if user is None or not user.active:
        raise HTTPException(401, "Sesión expirada")
    return _tokens(user.id)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user
