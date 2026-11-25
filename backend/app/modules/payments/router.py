from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.deps import DB, CurrentTenant, CurrentUser
from app.models import Payment
from app.modules.packages import service as pkgs
from app.schemas import PaymentCreate, PaymentOut

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("", response_model=PaymentOut, status_code=201)
def register_payment(data: PaymentCreate, db: DB, tenant: CurrentTenant, user: CurrentUser):
    """El operador confirma MANUALMENTE el cobro. Saturna no maneja dinero ni acepta capturas."""
    pkg = pkgs.get_owned(db, tenant.id, data.package_id)
    if pkg.state in ("DEVUELTO", "VENCIDO"):
        raise HTTPException(409, "El paquete no admite cobros")
    if db.scalar(select(Payment.id).where(Payment.package_id == pkg.id, Payment.tenant_id == tenant.id)):
        raise HTTPException(409, "El paquete ya tiene un cobro registrado")
    fees = pkgs.compute_fees(tenant, pkg)
    amount = data.amount if data.amount is not None else fees["total"]
    p = Payment(
        tenant_id=tenant.id,
        package_id=pkg.id,
        amount=amount,
        late_fee=fees["late"],
        method=data.method,
        registered_by=user.id,
    )
    db.add(p)
    pkgs.add_event(db, pkg.id, "COBRO", f"Bs {amount} ({data.method}) confirmado por el operador", user.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "El paquete ya tiene un cobro registrado") from None
    return p


@router.get("", response_model=list[PaymentOut])
def recent_payments(db: DB, tenant: CurrentTenant, limit: int = 50):
    stmt = (
        select(Payment)
        .where(Payment.tenant_id == tenant.id)
        .order_by(Payment.id.desc())
        .limit(min(limit, 200))
    )
    return db.scalars(stmt).all()
