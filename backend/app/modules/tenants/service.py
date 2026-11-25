from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.plans import METRIC_LIMIT_KEY, plan_of
from app.core.timeutil import utcnow
from app.models import Tenant, UsageCounter, User


def current_month() -> str:
    return utcnow().strftime("%Y-%m")


def get_counter(db: Session, tenant_id: int) -> UsageCounter:
    month = current_month()
    row = db.get(UsageCounter, (tenant_id, month))
    if row is None:
        row = UsageCounter(tenant_id=tenant_id, month=month, packages=0, notifications=0, ai_queries=0)
        db.add(row)
        db.flush()
    return row


def limit_reached(db: Session, tenant: Tenant, metric: str) -> bool:
    limit = plan_of(tenant.plan)[METRIC_LIMIT_KEY[metric]]
    if limit is None:
        return False
    return getattr(get_counter(db, tenant.id), metric) >= limit


def check_plan_limit(db: Session, tenant: Tenant, metric: str) -> None:
    """Se ejecuta ANTES de registrar paquetes, enviar avisos o consultar la IA."""
    if limit_reached(db, tenant, metric):
        label = {"packages": "paquetes", "notifications": "avisos", "ai_queries": "consultas de IA"}
        raise HTTPException(402, f"Alcanzaste el límite de {label[metric]} de tu plan este mes")


def increment(db: Session, tenant_id: int, metric: str, n: int = 1) -> None:
    row = get_counter(db, tenant_id)
    setattr(row, metric, getattr(row, metric) + n)


def check_operator_limit(db: Session, tenant: Tenant) -> None:
    limit = plan_of(tenant.plan)["max_operators"]
    if limit is None:
        return
    count = len(
        db.scalars(
            select(User.id).where(
                User.tenant_id == tenant.id, User.role == "operator", User.active.is_(True)
            )
        ).all()
    )
    if count >= limit:
        raise HTTPException(402, f"Tu plan permite hasta {limit} operador(es)")
