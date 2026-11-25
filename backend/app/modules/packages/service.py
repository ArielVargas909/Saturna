import math
import secrets
from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.phone import normalize_phone
from app.core.timeutil import utcnow
from app.models import Package, PackageEvent, Tenant
from app.modules.tenants import service as tenants

# Máquina de estados (sección 5 de la guía)
TRANSITIONS: dict[str, set[str]] = {
    "REGISTRADO": {"NOTIFICADO", "LISTO_PARA_RETIRO", "ESTANCADO", "DEVUELTO"},
    "NOTIFICADO": {"LISTO_PARA_RETIRO", "ESTANCADO", "DEVUELTO"},
    "LISTO_PARA_RETIRO": {"ENTREGADO", "NOTIFICADO", "ESTANCADO", "DEVUELTO"},
    "ESTANCADO": {"LISTO_PARA_RETIRO", "VENCIDO", "DEVUELTO"},
    "VENCIDO": {"DEVUELTO"},
    "ENTREGADO": set(),
    "DEVUELTO": set(),
}
OPEN_STATES = ("REGISTRADO", "NOTIFICADO", "LISTO_PARA_RETIRO", "ESTANCADO")
STALE_FROM = ("REGISTRADO", "NOTIFICADO", "LISTO_PARA_RETIRO")
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O/1/I para evitar confusiones
MIN_PAQUETES_SUGERENCIA = 3

LABELS = {
    "REGISTRADO": "Registrado",
    "NOTIFICADO": "Avisado al comprador",
    "LISTO_PARA_RETIRO": "Listo para retiro (QR emitido)",
    "ENTREGADO": "Entregado",
    "ESTANCADO": "Estancado (superó el plazo de custodia)",
    "DEVUELTO": "Devuelto",
    "VENCIDO": "Vencido",
}


def can_transition(current: str, new: str) -> bool:
    return new in TRANSITIONS.get(current, set())


def add_event(db: Session, package_id: int, type_: str, detail: str = "", user_id: int | None = None):
    db.add(PackageEvent(package_id=package_id, type=type_, detail=detail, user_id=user_id))


def change_state(db: Session, pkg: Package, new: str, user_id: int | None, detail: str = "") -> None:
    if pkg.state == new:
        return
    if new == "ENTREGADO":
        raise HTTPException(409, "ENTREGADO solo puede alcanzarse confirmando un QR válido")
    if not can_transition(pkg.state, new):
        raise HTTPException(409, f"Transición no permitida: {pkg.state} → {new}")
    add_event(db, pkg.id, "ESTADO", f"{pkg.state} → {new}. {detail}".strip(), user_id)
    pkg.state = new


def generate_code(db: Session) -> str:
    for _ in range(20):
        code = "SAT-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if db.scalar(select(Package.id).where(Package.code == code)) is None:
            return code
    raise HTTPException(500, "No se pudo generar un código único")


def register_package(db: Session, tenant: Tenant, user_id: int, data) -> Package:
    tenants.check_plan_limit(db, tenant, "packages")
    try:
        phone = normalize_phone(data.buyer_phone)
    except ValueError:
        raise HTTPException(422, "Teléfono del comprador inválido") from None
    now = utcnow()
    pkg = Package(
        tenant_id=tenant.id,
        code=generate_code(db),
        buyer_phone=phone,
        buyer_name=data.buyer_name.strip(),
        sender=data.sender.strip(),
        description=data.description.strip(),
        shelf_location=data.shelf_location.strip(),
        state="REGISTRADO",
        received_at=now,
        custody_deadline=now + timedelta(days=tenant.custody_days),
    )
    db.add(pkg)
    db.flush()
    add_event(db, pkg.id, "REGISTRO", "Paquete recibido en ventanilla", user_id)
    tenants.increment(db, tenant.id, "packages")
    db.commit()
    return pkg


def compute_fees(tenant: Tenant, pkg: Package) -> dict:
    now = utcnow()
    days_late = 0
    if now > pkg.custody_deadline:
        days_late = math.ceil((now - pkg.custody_deadline).total_seconds() / 86400)
    base = Decimal(tenant.custody_fee)
    late = Decimal(tenant.late_fee_per_day) * days_late
    return {"base": base, "late": late, "total": base + late, "days_late": days_late}


def refresh_stale(db: Session, tenant_id: int) -> None:
    """Marca como ESTANCADO los paquetes que superaron el plazo de custodia."""
    rows = db.scalars(
        select(Package).where(
            Package.tenant_id == tenant_id,
            Package.state.in_(STALE_FROM),
            Package.custody_deadline < utcnow(),
        )
    ).all()
    for p in rows:
        change_state(db, p, "ESTANCADO", None, "Superó el plazo de custodia")
    if rows:
        db.commit()


def suggest_buyer_names(db: Session, tenant_id: int, phone: str) -> list[str]:
    from sqlalchemy import func

    count = db.scalar(
        select(func.count()).select_from(Package).where(
            Package.tenant_id == tenant_id,
            Package.buyer_phone == phone,
            Package.buyer_name != "(eliminado)",
            Package.buyer_phone != "0000000000",
        )
    ) or 0
    if count < MIN_PAQUETES_SUGERENCIA:
        return []
    rows = db.execute(
        select(Package.buyer_name, func.count(Package.id))
        .where(
            Package.tenant_id == tenant_id,
            Package.buyer_phone == phone,
            Package.buyer_name != "",
            Package.buyer_name != "(eliminado)",
        )
        .group_by(Package.buyer_name)
        .order_by(func.count(Package.id).desc(), Package.buyer_name)
        .limit(3)
    ).all()
    return [name for name, _ in rows if name]


def get_owned(db: Session, tenant_id: int, package_id: int) -> Package:
    pkg = db.get(Package, package_id)
    if pkg is None or pkg.tenant_id != tenant_id:  # mismo 404: no revela existencia
        raise HTTPException(404, "Paquete no encontrado")
    return pkg


def update_package(db: Session, pkg: Package, data, user_id: int) -> Package:
    changed = []
    for field in ("buyer_name", "sender", "description", "shelf_location"):
        value = getattr(data, field)
        if value is not None and getattr(pkg, field) != value:
            setattr(pkg, field, value)
            changed.append(field)
    if changed:
        add_event(
            db,
            pkg.id,
            "ACTUALIZACION",
            "Campos actualizados: " + ", ".join(changed),
            user_id,
        )
        db.commit()
    return pkg


def search(db: Session, tenant_id: int, q: str | None, state: str | None, limit: int, offset: int):
    from sqlalchemy import func

    stmt = select(Package).where(Package.tenant_id == tenant_id)
    if state:
        stmt = stmt.where(Package.state == state)
    if q:
        like = f"%{q.strip()}%"
        folded_q = (
            q.strip().lower()
            .replace("á", "a").replace("é", "e").replace("í", "i")
            .replace("ó", "o").replace("ú", "u").replace("ü", "u").replace("ñ", "n")
        )
        def folded(column):
            expression = func.lower(column)
            for accented, plain in (
                ("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"),
                ("ü", "u"), ("ñ", "n"),
                ("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U"),
                ("Ü", "U"), ("Ñ", "N"),
            ):
                expression = func.replace(expression, accented, plain)
            return expression
        stmt = stmt.where(
            or_(
                Package.code.ilike(like),
                Package.buyer_phone.ilike(like),
                folded(Package.buyer_name).like(f"%{folded_q}%"),
                folded(Package.sender).like(f"%{folded_q}%"),
                folded(Package.description).like(f"%{folded_q}%"),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(stmt.order_by(Package.id.desc()).limit(limit).offset(offset)).all()
    return items, total
