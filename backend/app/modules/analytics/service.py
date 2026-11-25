import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.plans import plan_of
from app.core.timeutil import BO_OFFSET, to_local, today_start_utc, utcnow
from app.models import Package, Payment, Tenant
from app.modules.packages.service import OPEN_STATES

GRANULARITIES = ("day", "week", "month", "year")


def _f(x) -> float:
    return float(x or 0)


def revenue_between(db: Session, tenant_id: int, start: datetime, end: datetime | None = None) -> dict:
    end = end or utcnow() + timedelta(seconds=1)
    rows = db.execute(
        select(Payment.method, func.coalesce(func.sum(Payment.amount), 0), func.count())
        .where(Payment.tenant_id == tenant_id, Payment.created_at >= start, Payment.created_at < end)
        .group_by(Payment.method)
    ).all()
    out = {"total": 0.0, "cash": 0.0, "qr": 0.0, "count": 0}
    for method, amount, n in rows:
        out[method] = _f(amount)
        out["total"] += _f(amount)
        out["count"] += n
    return out


def cierre_caja(db: Session, tenant: Tenant, fecha: str) -> dict:
    try:
        local_date = datetime.strptime(fecha, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(422, "La fecha debe tener formato YYYY-MM-DD")
    start = local_date - BO_OFFSET
    end = start + timedelta(days=1)
    cobros = revenue_between(db, tenant.id, start, end)
    recargos = db.scalar(
        select(func.coalesce(func.sum(Payment.late_fee), 0)).where(
            Payment.tenant_id == tenant.id,
            Payment.created_at >= start,
            Payment.created_at < end,
        )
    )
    entregas = db.scalar(
        select(func.count()).where(
            Package.tenant_id == tenant.id,
            Package.delivered_at >= start,
            Package.delivered_at < end,
        )
    )
    pendientes = db.scalar(
        select(func.count()).where(
            Package.tenant_id == tenant.id,
            Package.state.in_(OPEN_STATES),
        )
    )
    estancados = db.scalar(
        select(func.count()).where(
            Package.tenant_id == tenant.id,
            Package.state == "ESTANCADO",
        )
    )
    return {
        "fecha": fecha,
        "total_cobrado": cobros["total"],
        "efectivo": cobros["cash"],
        "qr": cobros["qr"],
        "cantidad_entregas": entregas or 0,
        "recargos_cobrados": _f(recargos),
        "paquetes_pendientes": pendientes or 0,
        "paquetes_estancados": estancados or 0,
    }


def summary(db: Session, tenant: Tenant) -> dict:
    tid = tenant.id
    by_state = dict(
        db.execute(
            select(Package.state, func.count()).where(Package.tenant_id == tid).group_by(Package.state)
        ).all()
    )
    day0 = today_start_utc()
    received_today = db.scalar(
        select(func.count()).where(Package.tenant_id == tid, Package.received_at >= day0)
    )
    delivered_today = db.scalar(
        select(func.count()).where(Package.tenant_id == tid, Package.delivered_at >= day0)
    )
    late = db.scalar(
        select(func.count()).where(
            Package.tenant_id == tid, Package.state.in_(OPEN_STATES), Package.custody_deadline < utcnow()
        )
    )
    delivered = db.execute(
        select(Package.received_at, Package.delivered_at).where(
            Package.tenant_id == tid,
            Package.state == "ENTREGADO",
            Package.delivered_at >= utcnow() - timedelta(days=30),
        )
    ).all()
    avg_hours = (
        sum((d - r).total_seconds() for r, d in delivered) / len(delivered) / 3600 if delivered else 0
    )
    return {
        "by_state": by_state,
        "in_custody": sum(by_state.get(s, 0) for s in OPEN_STATES),
        "received_today": received_today,
        "delivered_today": delivered_today,
        "late_packages": late,
        "avg_stay_hours": round(avg_hours, 1),
        "revenue_today": revenue_between(db, tid, day0),
        "note": "Los importes son cobros registrados, no utilidad neta.",
    }


def _bucket(dt: datetime, gran: str) -> str:
    local = to_local(dt)
    if gran == "day":
        return local.strftime("%Y-%m-%d")
    if gran == "week":
        return (local - timedelta(days=local.weekday())).strftime("%Y-%m-%d")
    if gran == "month":
        return local.strftime("%Y-%m")
    return local.strftime("%Y")


def _keys(gran: str) -> tuple[list[str], datetime]:
    now = to_local(utcnow())
    if gran == "day":
        ks = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(13, -1, -1)]
    elif gran == "week":
        monday = now - timedelta(days=now.weekday())
        ks = [(monday - timedelta(weeks=i)).strftime("%Y-%m-%d") for i in range(11, -1, -1)]
    elif gran == "month":
        ks, y, m = [], now.year, now.month
        for _ in range(12):
            ks.append(f"{y}-{m:02d}")
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        ks.reverse()
    else:
        ks = [str(now.year - i) for i in range(4, -1, -1)]
    first = ks[0]
    fmt = {"day": "%Y-%m-%d", "week": "%Y-%m-%d", "month": "%Y-%m", "year": "%Y"}[gran]
    start_local = datetime.strptime(first, fmt)
    return ks, start_local - BO_OFFSET  # inicio del primer bucket, en UTC


def ensure_granularity(tenant: Tenant, gran: str) -> None:
    if gran not in GRANULARITIES:
        raise HTTPException(422, "Granularidad inválida")
    if gran not in plan_of(tenant.plan)["granularities"]:
        raise HTTPException(403, "Tu plan no incluye esta gráfica. Mejora tu plan para verla.")


def revenue_series(db: Session, tenant: Tenant, gran: str) -> list[dict]:
    ensure_granularity(tenant, gran)
    keys, start = _keys(gran)
    rows = db.execute(
        select(Payment.created_at, Payment.method, Payment.amount).where(
            Payment.tenant_id == tenant.id, Payment.created_at >= start
        )
    ).all()
    acc = {k: {"bucket": k, "total": 0.0, "cash": 0.0, "qr": 0.0, "count": 0} for k in keys}
    for created, method, amount in rows:
        b = acc.get(_bucket(created, gran))
        if b is not None:
            b["total"] += _f(amount)
            b[method] += _f(amount)
            b["count"] += 1
    return list(acc.values())


def export_csv(db: Session, tenant: Tenant) -> str:
    if not plan_of(tenant.plan)["export"]:
        raise HTTPException(403, "La exportación de reportes es del plan Premium")
    rows = db.execute(
        select(Payment, Package.code)
        .join(Package, Package.id == Payment.package_id)
        .where(Payment.tenant_id == tenant.id)
        .order_by(Payment.id)
    ).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["fecha_local", "codigo_paquete", "metodo", "monto_bs", "recargo_bs"])
    for p, code in rows:
        w.writerow([to_local(p.created_at).strftime("%Y-%m-%d %H:%M"), code, p.method,
                    f"{Decimal(p.amount):.2f}", f"{Decimal(p.late_fee):.2f}"])
    return buf.getvalue()
