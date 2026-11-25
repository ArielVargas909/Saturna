from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.core.deps import DB, CurrentTenant, CurrentUser, Owner
from app.core.phone import normalize_optional
from app.core.plans import PLANS, plan_of
from app.core.security import hash_password
from app.models import User
from app.modules.tenants import service
from app.schemas import PlanChange, TenantOut, TenantUpdate, UserCreate, UserOut

router = APIRouter(tags=["tenants"])


@router.get("/plans")
def list_plans():
    return PLANS


@router.get("/tenants/me", response_model=TenantOut)
def my_tenant(tenant: CurrentTenant):
    return tenant


@router.patch("/tenants/me", response_model=TenantOut)
def update_tenant(data: TenantUpdate, db: DB, tenant: CurrentTenant, _: Owner):
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(tenant, k, v)
    db.commit()
    return tenant


@router.post("/tenants/me/plan", response_model=TenantOut)
def change_plan(data: PlanChange, db: DB, tenant: CurrentTenant, _: Owner):
    """Cambio manual de plan. El cobro automático de suscripciones queda fuera del MVP."""
    tenant.plan = data.plan
    db.commit()
    return tenant


@router.get("/tenants/me/usage")
def usage(db: DB, tenant: CurrentTenant):
    c = service.get_counter(db, tenant.id)
    db.commit()
    p = plan_of(tenant.plan)
    return {
        "month": c.month,
        "plan": tenant.plan,
        "packages": {"used": c.packages, "limit": p["max_packages"]},
        "notifications": {"used": c.notifications, "limit": p["max_notifications"]},
        "ai_queries": {"used": c.ai_queries, "limit": p["max_ai"]},
        "operators_limit": p["max_operators"],
        "granularities": p["granularities"],
        "export": p["export"],
    }


# ---- usuarios (operadores) ----
@router.get("/users", response_model=list[UserOut])
def list_users(db: DB, user: CurrentUser):
    return db.scalars(select(User).where(User.tenant_id == user.tenant_id).order_by(User.id)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_operator(data: UserCreate, db: DB, tenant: CurrentTenant, _: Owner):
    service.check_operator_limit(db, tenant)
    if db.scalar(select(User.id).where(User.email == data.email.lower())):
        raise HTTPException(409, "Ese correo ya está registrado")
    u = User(
        tenant_id=tenant.id,
        name=data.name,
        email=data.email.lower(),
        password_hash=hash_password(data.password),
        role="operator",
        phone=normalize_optional(data.phone),
    )
    db.add(u)
    db.commit()
    return u


@router.patch("/users/{user_id}/toggle", response_model=UserOut)
def toggle_user(user_id: int, db: DB, tenant: CurrentTenant, owner: Owner):
    u = db.get(User, user_id)
    if u is None or u.tenant_id != tenant.id or u.role == "owner":
        raise HTTPException(404, "Usuario no encontrado")
    if not u.active:
        service.check_operator_limit(db, tenant)
    u.active = not u.active
    db.commit()
    return u
