"""Herramientas del agente. REGLA DE ORO: el modelo NO toca la base de datos.

Solo invoca estas funciones; cada una filtra por tenant_id / teléfono que vienen del
SERVIDOR (objeto Ctx), nunca de los argumentos que escribe el modelo o el usuario.
"""
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.plans import plan_of
from app.core.text import title_name
from app.core.timeutil import to_local, today_start_utc, utcnow
from app.models import Package, Tenant
from app.modules.analytics import service as analytics
from app.modules.packages import service as pkgs
from app.modules.qr import service as qr


@dataclass
class Ctx:
    db: Session
    phone: str
    role: str  # buyer | owner | operator
    tenant_id: int | None = None  # solo personal de la paquetería
    user_id: int | None = None
    tenant_scope: int | None = None  # restringe consultas del comprador a un solo tenant
    outbox: list[dict] = field(default_factory=list)
    last_package_id: int | None = None
    last_package_code: str = ""


def _fmt(dt) -> str:
    return to_local(dt).strftime("%d/%m/%Y %H:%M")


def _find(ctx: Ctx, code: str) -> Package | None:
    code = (code or "").strip().upper()
    stmt = select(Package).where(Package.code == code)
    if ctx.role == "buyer":
        stmt = stmt.where(Package.buyer_phone == ctx.phone)
        if ctx.tenant_scope:
            stmt = stmt.where(Package.tenant_id == ctx.tenant_scope)
    else:
        stmt = stmt.where(Package.tenant_id == ctx.tenant_id)
    return ctx.db.scalar(stmt)


def _maps_link(t: Tenant) -> str:
    if t.maps_url:
        return t.maps_url
    if t.latitude is not None and t.longitude is not None:
        return f"https://maps.google.com/?q={t.latitude},{t.longitude}"
    return ""


def _resolve_tenants(ctx: Ctx, codigo: str = "") -> list[Tenant]:
    if ctx.role != "buyer":
        t = ctx.db.get(Tenant, ctx.tenant_id)
        return [t] if t is not None else []
    stmt = select(Package.tenant_id).where(Package.buyer_phone == ctx.phone)
    if codigo:
        stmt = stmt.where(Package.code == codigo.strip().upper())
    if ctx.tenant_scope:
        stmt = stmt.where(Package.tenant_id == ctx.tenant_scope)
    ids = set(ctx.db.scalars(stmt).all())
    return [t for i in ids if (t := ctx.db.get(Tenant, i)) is not None]


def consultar_estado_paquete(ctx: Ctx, codigo: str = "") -> dict:
    pkg = _find(ctx, codigo)
    if pkg is None:
        return {"error": "No encontré un paquete con ese código asociado a tu número."}
    ctx.last_package_id = pkg.id
    ctx.last_package_code = pkg.code
    tenant = ctx.db.get(Tenant, pkg.tenant_id)
    out = {
        "codigo": pkg.code,
        "estado": pkgs.LABELS.get(pkg.state, pkg.state),
        "paqueteria": tenant.name,
        "llego": _fmt(pkg.received_at),
        "plazo_custodia_hasta": _fmt(pkg.custody_deadline),
    }
    if pkg.scheduled_pickup_at:
        out["horario_retiro_acordado"] = pkg.scheduled_pickup_at
    if pkg.state in pkgs.OPEN_STATES:
        fees = pkgs.compute_fees(tenant, pkg)
        out["tarifa_base_bs"] = float(fees["base"])
        out["recargo_bs"] = float(fees["late"])
        out["cobro_estimado_bs"] = float(fees["total"])
        out["dias_de_retraso"] = fees["days_late"]
    return out


def listar_mis_paquetes(ctx: Ctx) -> dict:
    stmt = select(Package).where(Package.state.in_(pkgs.OPEN_STATES))
    if ctx.role == "buyer":
        stmt = stmt.where(Package.buyer_phone == ctx.phone)
        if ctx.tenant_scope:
            stmt = stmt.where(Package.tenant_id == ctx.tenant_scope)
    else:
        stmt = stmt.where(Package.tenant_id == ctx.tenant_id)
    rows = ctx.db.scalars(stmt.order_by(Package.id.desc()).limit(10)).all()
    if len(rows) == 1:
        ctx.last_package_id = rows[0].id
        ctx.last_package_code = rows[0].code
    return {
        "paquetes": [
            {
                "codigo": p.code,
                "estado": pkgs.LABELS.get(p.state, p.state),
                "plazo_hasta": _fmt(p.custody_deadline),
                **({"horario_retiro_acordado": p.scheduled_pickup_at} if p.scheduled_pickup_at else {}),
            }
            for p in rows
        ]
    }


def solicitar_qr_retiro(ctx: Ctx, codigo: str = "") -> dict:
    if ctx.role != "buyer":
        return {"error": "Solo el comprador puede pedir su QR de retiro."}
    pkg = _find(ctx, codigo)
    if pkg is None:
        return {"error": "No encontré un paquete con ese código asociado a tu número."}
    if pkg.state not in pkgs.OPEN_STATES:
        return {"error": "Ese paquete ya fue entregado, devuelto o venció."}
    ctx.last_package_id = pkg.id
    ctx.last_package_code = pkg.code
    tenant = ctx.db.get(Tenant, pkg.tenant_id)
    try:
        token, expires = qr.issue_token(ctx.db, tenant, pkg, None)
    except Exception:  # paquete cerrado, etc.
        return {"error": "Ese paquete ya fue entregado o devuelto."}
    fees = pkgs.compute_fees(tenant, pkg)
    url = f"{get_settings().public_base_url.rstrip('/')}/qr/image/{token}.png"
    ctx.outbox.append({"type": "image", "url": url, "caption": f"QR de retiro {pkg.code}"})
    return {
        "ok": True,
        "codigo": pkg.code,
        "vence": _fmt(expires),
        "cobro_estimado_bs": float(fees["total"]),
        "dias_de_retraso": fees["days_late"],
        "nota": "El QR se envió como imagen; sirve una sola vez.",
    }


def agendar_retiro(ctx: Ctx, codigo: str = "", horario: str = "") -> dict:
    """Acuerda y guarda el horario estimado de retiro de un paquete abierto del comprador."""
    if ctx.role != "buyer":
        return {"error": "Solo el comprador puede agendar el horario de retiro."}
    clean_schedule = " ".join((horario or "").split())[:120]
    if len(clean_schedule) < 3:
        return {"error": "Indica qué día y hora aproximada pasarás a recoger tu paquete."}
    pkg = _find(ctx, codigo)
    if pkg is None:
        return {"error": "No encontré un paquete con ese código asociado a tu número."}
    if pkg.state not in pkgs.OPEN_STATES:
        return {"error": "Ese paquete ya fue entregado, devuelto o venció."}
    ctx.last_package_id = pkg.id
    ctx.last_package_code = pkg.code
    tenant = ctx.db.get(Tenant, pkg.tenant_id)
    pkg.scheduled_pickup_at = clean_schedule
    pkgs.add_event(ctx.db, pkg.id, "CITA_RETIRO", f"Horario de retiro acordado: {clean_schedule}", None)
    ctx.db.commit()
    return {
        "ok": True,
        "codigo": pkg.code,
        "horario_acordado": clean_schedule,
        "paqueteria": tenant.name,
        "horario_atencion": tenant.opening_hours,
        "direccion": tenant.address,
        "nota": "Horario registrado para el equipo de ventanilla. Cuando vayas, pide tu QR de retiro.",
    }


def _tenant_conditions(t: Tenant) -> dict:
    return {
        "nombre": t.name,
        "direccion": t.address,
        "horario": t.opening_hours,
        "maps_url": _maps_link(t),
        "dias_custodia": t.custody_days,
        "tarifa_custodia_bs": float(t.custody_fee),
        "recargo_diario_bs": float(t.late_fee_per_day),
        "condiciones_retiro": "Presenta tu QR de retiro de un solo uso en ventanilla y confirma el pago (efectivo o QR).",
    }


def horario_de_atencion(ctx: Ctx, codigo: str = "") -> dict:
    tenants = _resolve_tenants(ctx, codigo)
    return {"paqueterias": [_tenant_conditions(t) for t in tenants]}


def enviar_ubicacion(ctx: Ctx, codigo: str = "") -> dict:
    """Devuelve la ubicación de la paquetería y agrega un pin GPS al outbox si hay coordenadas."""
    tenants = _resolve_tenants(ctx, codigo)
    if not tenants:
        return {"error": "No encontré paquetes asociados a tu número."}
    items = []
    for t in tenants:
        maps_url = _maps_link(t)
        pin = t.latitude is not None and t.longitude is not None
        if pin or maps_url:
            ctx.outbox.append(
                {
                    "type": "location",
                    "latitude": t.latitude,
                    "longitude": t.longitude,
                    "name": t.name,
                    "address": t.address,
                    "maps_url": maps_url,
                }
            )
        items.append(
            {
                "nombre": t.name,
                "direccion": t.address,
                "horario": t.opening_hours,
                "maps_url": maps_url,
                "pin_enviado": pin,
            }
        )
    return {"ubicaciones": items}


def _premium_only(ctx: Ctx) -> dict | None:
    if ctx.role != "owner":
        return {"error": "Esta información es solo para el propietario."}
    tenant = ctx.db.get(Tenant, ctx.tenant_id)
    if not plan_of(tenant.plan)["ai_advanced"]:
        return {"error": "El copiloto financiero es parte del plan Premium."}
    return None


def resumen_cobros(ctx: Ctx, periodo: str = "hoy") -> dict:
    if (err := _premium_only(ctx)) is not None:
        return err
    now = utcnow()
    start = {"hoy": today_start_utc(), "semana": today_start_utc() - timedelta(days=6),
             "mes": today_start_utc() - timedelta(days=29)}.get(periodo, today_start_utc())
    data = analytics.revenue_between(ctx.db, ctx.tenant_id, start, now + timedelta(seconds=1))
    return {
        "periodo": periodo if periodo in ("hoy", "semana", "mes") else "hoy",
        "total_cobrado_bs": data["total"],
        "efectivo_bs": data["cash"],
        "qr_bs": data["qr"],
        "cantidad_de_cobros": data["count"],
        "aclaracion": "Son cobros registrados, no utilidad neta.",
    }


def paquetes_estancados(ctx: Ctx) -> dict:
    if (err := _premium_only(ctx)) is not None:
        return err
    soon = utcnow() + timedelta(days=1)
    rows = ctx.db.scalars(
        select(Package)
        .where(Package.tenant_id == ctx.tenant_id, Package.state.in_(pkgs.OPEN_STATES),
               Package.custody_deadline < soon)
        .order_by(Package.custody_deadline)
        .limit(10)
    ).all()
    return {"paquetes": [{"codigo": p.code, "comprador": title_name(p.buyer_name) or p.buyer_phone,
                          "estado": pkgs.LABELS.get(p.state, p.state), "plazo_hasta": _fmt(p.custody_deadline)}
                         for p in rows]}


REGISTRY = {
    f.__name__: f
    for f in (
        consultar_estado_paquete,
        listar_mis_paquetes,
        solicitar_qr_retiro,
        agendar_retiro,
        horario_de_atencion,
        enviar_ubicacion,
        resumen_cobros,
        paquetes_estancados,
    )
}

_CODE = {"type": "object", "properties": {"codigo": {"type": "string", "description": "Código SAT-XXXXXX"}},
         "required": ["codigo"]}
_NONE = {"type": "object", "properties": {}}

SCHEMAS = {
    "consultar_estado_paquete": ("Devuelve estado, llegada, plazo, horario acordado y cobro estimado de un paquete.", _CODE),
    "listar_mis_paquetes": ("Lista los paquetes pendientes asociados al número de quien escribe.", _NONE),
    "solicitar_qr_retiro": ("Emite el QR de un solo uso para retirar un paquete y lo envía por WhatsApp.", _CODE),
    "agendar_retiro": (
        "Guarda el día y hora acordados con el comprador para recoger su paquete.",
        {
            "type": "object",
            "properties": {
                "codigo": {"type": "string", "description": "Código SAT-XXXXXX"},
                "horario": {"type": "string", "description": "Día y hora aproximada de retiro, ej. Mañana 16:00"},
            },
            "required": ["codigo", "horario"],
        },
    ),
    "horario_de_atencion": ("Horario, dirección, tarifas y condiciones de retiro de la paquetería.",
                            {"type": "object", "properties": {"codigo": {"type": "string"}}}),
    "enviar_ubicacion": ("Envía la dirección, enlace de Google Maps y pin de ubicación GPS de la paquetería.",
                         {"type": "object", "properties": {"codigo": {"type": "string"}}}),
    "resumen_cobros": ("Resumen de cobros registrados (solo propietario).",
                       {"type": "object", "properties": {"periodo": {"type": "string", "enum": ["hoy", "semana", "mes"]}}}),
    "paquetes_estancados": ("Paquetes vencidos o por vencer (solo propietario).", _NONE),
}
ALLOWED = {
    "buyer": [
        "consultar_estado_paquete",
        "listar_mis_paquetes",
        "solicitar_qr_retiro",
        "agendar_retiro",
        "horario_de_atencion",
        "enviar_ubicacion",
    ],
    "operator": ["consultar_estado_paquete", "listar_mis_paquetes", "horario_de_atencion", "enviar_ubicacion"],
    "owner": [
        "consultar_estado_paquete",
        "listar_mis_paquetes",
        "horario_de_atencion",
        "enviar_ubicacion",
        "resumen_cobros",
        "paquetes_estancados",
    ],
}


def tool_schemas(role: str) -> list[dict]:
    return [{"name": n, "description": SCHEMAS[n][0], "input_schema": SCHEMAS[n][1]} for n in ALLOWED[role]]


def execute(ctx: Ctx, name: str, args: dict) -> dict:
    """Ejecuta una herramienta. Solo las permitidas al rol; los argumentos se filtran."""
    if name not in ALLOWED[ctx.role]:
        return {"error": "Herramienta no disponible."}
    fn = REGISTRY[name]
    allowed = {"codigo", "periodo", "horario"} & set(fn.__code__.co_varnames[: fn.__code__.co_argcount])
    clean = {k: str(v)[:120] for k, v in (args or {}).items() if k in allowed}  # tenant_id jamás pasa
    return fn(ctx, **clean)
