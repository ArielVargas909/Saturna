import inspect
import logging
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.text import title_name
from app.core.timeutil import to_local, utcnow
from app.db.session import SessionLocal
from app.models import Notification, Package, Tenant
from app.modules.notifications import whatsapp
from app.modules.packages import service as pkgs
from app.modules.tenants import service as tenants

log = logging.getLogger("saturna.notifications")

# Nombres posibles de campos y funciones (se prueban en este orden)
SENDER_FIELDS = ("sender_name", "sender", "remitente", "seller_name", "shop_name")
ADDRESS_FIELDS = ("address", "direccion", "location", "ubicacion")
ISSUE_NAMES = ("issue_qr", "emit_qr", "emitir_qr", "issue_token", "create_token", "create_qr", "generate_token", "issue")
PNG_NAMES = (
    "render_png",
    "qr_png",
    "make_png",
    "generate_png",
    "png_bytes",
    "qr_image",
    "render_qr",
    "build_png",
    "qr_png_bytes",
)
TOKEN_ATTRS = ("token", "raw_token", "plain_token", "value")


def _first_attr(obj, names, default=""):
    for n in names:
        v = getattr(obj, n, None)
        if v:
            return str(v)
    return default


def _call(fn, **available):
    """Llama a fn pasando solo los parámetros que acepta, por nombre."""
    params = inspect.signature(fn).parameters
    return fn(**{k: v for k, v in available.items() if k in params})


def _extract_token(result):
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for n in TOKEN_ATTRS:
            if isinstance(result.get(n), str):
                return result[n]
    if isinstance(result, (tuple, list)):
        for item in result:
            t = _extract_token(item)
            if t:
                return t
    for n in TOKEN_ATTRS:
        v = getattr(result, n, None)
        if isinstance(v, str):
            return v
    return None


def _qr_png(db: Session, pkg: Package, tenant: Tenant, user_id: int | None, existing_token: str | None = None) -> bytes:
    """Devuelve la imagen PNG del QR (usando un token ya emitido o emitiendo uno nuevo)."""
    from app.modules.qr import service as qr_service  # import tardío para evitar ciclos

    public = [n for n in dir(qr_service) if not n.startswith("_") and callable(getattr(qr_service, n))]
    render = next((getattr(qr_service, n) for n in PNG_NAMES if hasattr(qr_service, n)), None)
    if render is None:
        raise RuntimeError("No se encontro como renderizar el QR. Funciones en qr/service.py: " + ", ".join(public))
    token = existing_token
    if not token:
        issue = next((getattr(qr_service, n) for n in ISSUE_NAMES if hasattr(qr_service, n)), None)
        if issue is None:
            raise RuntimeError("No se encontro como generar el QR. Funciones en qr/service.py: " + ", ".join(public))
        issued = _call(issue, db=db, pkg=pkg, package=pkg, package_id=pkg.id, tenant=tenant, user_id=user_id)
        token = _extract_token(issued)
        if not token:
            raise RuntimeError("El QR se emitio pero no se pudo leer el token")
    png = render(token)
    if hasattr(png, "getvalue"):
        png = png.getvalue()
    if not isinstance(png, (bytes, bytearray)):
        raise RuntimeError("La funcion del QR no devolvio una imagen PNG")
    return bytes(png)


def _format_pickup_summary(
    pkg: Package,
    tenant: Tenant,
    *,
    has_qr: bool = False,
    expires_at: datetime | None = None,
) -> str:
    fees = pkgs.compute_fees(tenant, pkg)
    buyer = title_name(pkg.buyer_name) or "Cliente"
    state_label = pkgs.LABELS.get(pkg.state, pkg.state)
    deadline = to_local(pkg.custody_deadline).strftime("%d/%m/%Y %H:%M")
    parts = [
        f"Hola {buyer}, tu paquete {pkg.code} en {tenant.name} está en estado: {state_label}.",
        f"Plazo de custodia hasta {deadline}.",
    ]
    if fees["days_late"] > 0:
        parts.append(
            f"Cobro estimado: Bs {fees['total']:.2f} "
            f"(custodia Bs {fees['base']:.2f} + recargo Bs {fees['late']:.2f} por {fees['days_late']} día(s) de demora)."
        )
    else:
        parts.append(f"Cobro de custodia: Bs {fees['total']:.2f}.")
    if has_qr:
        exp_txt = f" (vence {to_local(expires_at).strftime('%d/%m/%Y %H:%M')})" if expires_at else ""
        parts.append(f"Adjuntamos tu QR de retiro de un solo uso{exp_txt}.")
    else:
        parts.append("Responde a este chat con tu código para recibir tu QR de retiro.")
    return " ".join(parts)


def send_arrival(db: Session, pkg: Package, tenant: Tenant, user_id: int | None = None) -> Notification:
    """Envía el aviso de llegada respetando el límite mensual del plan."""
    note = Notification(tenant_id=tenant.id, package_id=pkg.id, kind="aviso_llegada", status="queued")
    db.add(note)
    s = get_settings()
    if whatsapp.is_mock():
        summary = _format_pickup_summary(pkg, tenant, has_qr=False)
        buyer_name = title_name(pkg.buyer_name) or "Cliente"
        whatsapp.send_template(pkg.buyer_phone, s.whatsapp_template_arrival, [buyer_name, pkg.code, tenant.name])
        note.status = "simulated"
        note.meta_message_id = None
        note.detail = f"Sin credenciales de WhatsApp; envío simulado. {summary}"[:240]
        pkgs.add_event(db, pkg.id, "AVISO_SIMULADO", note.detail, user_id)
        db.commit()
        return note
    if tenants.limit_reached(db, tenant, "notifications"):
        note.status, note.detail = "failed", "limite_plan"
        pkgs.add_event(db, pkg.id, "AVISO_FALLIDO", "Límite mensual de avisos del plan alcanzado", user_id)
        db.commit()
        return note

    template = s.whatsapp_template_arrival
    buyer = title_name(pkg.buyer_name) or "Cliente"

    if template.endswith("_qr"):  # Plantilla con QR: {{1}} comprador, {{2}} remitente, {{3}} paquetería y dirección
        sender = _first_attr(pkg, SENDER_FIELDS, "una tienda")
        place = tenant.name
        address = _first_attr(tenant, ADDRESS_FIELDS)
        if address:
            place = f"{tenant.name}, {address}"
        try:
            png = _qr_png(db, pkg, tenant, user_id)
            media = whatsapp.upload_media(png)
            if not media.ok:
                raise RuntimeError(f"No se pudo subir el QR a Meta: {media.detail}")
            res = whatsapp.send_template_image(pkg.buyer_phone, template, [buyer, sender, place], media.message_id)
        except Exception as exc:  # el error queda visible en el paquete
            res = whatsapp.SendResult(False, detail=str(exc)[:300])
    else:
        # Plantilla simple sin imagen: {{1}} comprador, {{2}} código, {{3}} paquetería
        res = whatsapp.send_template(pkg.buyer_phone, template, [buyer, pkg.code, tenant.name])

    real_sent = res.ok and bool(res.message_id) and not res.simulated and not res.message_id.startswith("mock-")
    note.status = "sent" if real_sent else "failed"
    note.meta_message_id = res.message_id if real_sent else None
    note.detail = res.detail[:240]
    if real_sent:
        tenants.increment(db, tenant.id, "notifications")
        if pkg.state == "REGISTRADO":
            pkgs.change_state(db, pkg, "NOTIFICADO", user_id, "Aviso enviado por WhatsApp")
    else:
        pkgs.add_event(db, pkg.id, "AVISO_FALLIDO", res.detail[:240], user_id)
    db.commit()
    return note


def send_pickup_ready(
    db: Session,
    pkg: Package,
    tenant: Tenant,
    user_id: int | None = None,
    *,
    token: str | None = None,
    expires_at: datetime | None = None,
) -> Notification:
    """Envía un aviso proactivo cuando el paquete pasa a NOTIFICADO / LISTO_PARA_RETIRO o se emite su QR."""
    note = Notification(tenant_id=tenant.id, package_id=pkg.id, kind="aviso_retiro", status="queued")
    db.add(note)
    s = get_settings()
    summary = _format_pickup_summary(pkg, tenant, has_qr=bool(token), expires_at=expires_at)

    if whatsapp.is_mock():
        whatsapp.send_text(pkg.buyer_phone, summary)
        if token:
            qr_url = f"{s.public_base_url.rstrip('/')}/qr/image/{token}.png"
            whatsapp.send_image(pkg.buyer_phone, qr_url, f"QR de retiro {pkg.code}")
        note.status = "simulated"
        note.meta_message_id = None
        note.detail = summary[:240]
        pkgs.add_event(db, pkg.id, "AVISO_SIMULADO", summary[:240], user_id)
        db.commit()
        return note

    if tenants.limit_reached(db, tenant, "notifications"):
        note.status, note.detail = "failed", "limite_plan"
        pkgs.add_event(db, pkg.id, "AVISO_FALLIDO", "Límite mensual de avisos del plan alcanzado", user_id)
        db.commit()
        return note

    template = s.whatsapp_template_arrival
    buyer = title_name(pkg.buyer_name) or "Cliente"
    fallback_params = [buyer, pkg.code, tenant.name]

    if token and template.endswith("_qr"):
        sender = _first_attr(pkg, SENDER_FIELDS, "una tienda")
        place = tenant.name
        address = _first_attr(tenant, ADDRESS_FIELDS)
        if address:
            place = f"{tenant.name}, {address}"
        try:
            png = _qr_png(db, pkg, tenant, user_id, existing_token=token)
            media = whatsapp.upload_media(png)
            if not media.ok:
                raise RuntimeError(f"No se pudo subir el QR a Meta: {media.detail}")
            res = whatsapp.send_template_image(pkg.buyer_phone, template, [buyer, sender, place], media.message_id)
        except Exception as exc:
            res = whatsapp.SendResult(False, detail=str(exc)[:300])
    else:
        res = whatsapp.send_text(
            pkg.buyer_phone,
            summary,
            fallback_template=template,
            fallback_params=fallback_params,
        )
        if res.ok and token and not res.fallback_used:
            qr_url = f"{s.public_base_url.rstrip('/')}/qr/image/{token}.png"
            img_res = whatsapp.send_image(
                pkg.buyer_phone,
                qr_url,
                f"QR de retiro {pkg.code}",
                fallback_template=template,
                fallback_params=fallback_params,
            )
            if not img_res.ok:
                res.detail = f"Texto enviado; imagen QR falló: {img_res.detail}"[:240]

    real_sent = res.ok and bool(res.message_id) and not res.simulated and not res.message_id.startswith("mock-")
    note.status = "sent" if real_sent else "failed"
    note.meta_message_id = res.message_id if real_sent else None
    note.detail = (res.detail or summary)[:240]
    if real_sent:
        tenants.increment(db, tenant.id, "notifications")
        pkgs.add_event(db, pkg.id, "AVISO_RETIRO", note.detail, user_id)
    else:
        pkgs.add_event(db, pkg.id, "AVISO_FALLIDO", note.detail, user_id)
    db.commit()
    return note


def send_qr_to_buyer(
    db: Session,
    pkg: Package,
    tenant: Tenant,
    user_id: int | None,
    token: str,
    expires_at: datetime,
) -> Notification:
    """Envía directamente al comprador por WhatsApp el QR de retiro recién emitido por el encargado."""
    note = Notification(tenant_id=tenant.id, package_id=pkg.id, kind="qr_retiro", status="queued")
    db.add(note)
    s = get_settings()
    exp_str = to_local(expires_at).strftime("%d/%m/%Y %H:%M")
    fees = pkgs.compute_fees(tenant, pkg)
    caption = (
        f"QR de retiro para tu paquete {pkg.code} en {tenant.name}. "
        f"Cobro estimado: Bs {fees['total']:.2f}. Vence el {exp_str} (uso único)."
    )

    if whatsapp.is_mock():
        qr_url = f"{s.public_base_url.rstrip('/')}/qr/image/{token}.png"
        whatsapp.send_image(pkg.buyer_phone, qr_url, caption)
        note.status = "simulated"
        note.meta_message_id = None
        note.detail = f"Sin credenciales de WhatsApp; QR simulado. {caption}"[:240]
        pkgs.add_event(db, pkg.id, "QR_SIMULADO", note.detail, user_id)
        db.commit()
        return note

    if tenants.limit_reached(db, tenant, "notifications"):
        note.status, note.detail = "failed", "limite_plan"
        pkgs.add_event(db, pkg.id, "AVISO_FALLIDO", "Límite mensual de avisos del plan alcanzado", user_id)
        db.commit()
        return note

    template = s.whatsapp_template_arrival
    buyer = title_name(pkg.buyer_name) or "Cliente"
    if template.endswith("_qr"):
        sender = _first_attr(pkg, SENDER_FIELDS, "una tienda")
        address = _first_attr(tenant, ADDRESS_FIELDS)
        place = f"{tenant.name}, {address}" if address else tenant.name
        fallback_params = [buyer, sender, place]
    else:
        fallback_params = [buyer, pkg.code, tenant.name]

    try:
        png = _qr_png(db, pkg, tenant, user_id, existing_token=token)
        media = whatsapp.upload_media(png)
        if not media.ok:
            raise RuntimeError(f"No se pudo subir el QR a Meta: {media.detail}")
        # Intenta enviar primero como imagen libre (gratis en ventana 24h); si expiró 24h cae a plantilla aprobada.
        res = whatsapp.send_image_media(
            pkg.buyer_phone,
            media.message_id,
            caption,
            fallback_template=template,
            fallback_params=fallback_params,
            fallback_media_id=media.message_id,
        )
    except Exception as exc:
        res = whatsapp.SendResult(False, detail=str(exc)[:300])

    real_sent = res.ok and bool(res.message_id) and not res.simulated and not res.message_id.startswith("mock-")
    note.status = "sent" if real_sent else "failed"
    note.meta_message_id = res.message_id if real_sent else None
    note.detail = (res.detail or caption)[:240]
    if real_sent:
        tenants.increment(db, tenant.id, "notifications")
        pkgs.add_event(db, pkg.id, "QR_ENVIADO", f"QR de retiro enviado al comprador por WhatsApp ({note.detail})"[:240], user_id)
    else:
        pkgs.add_event(db, pkg.id, "AVISO_FALLIDO", note.detail, user_id)
    db.commit()
    return note


def send_arrival_task(package_id: int) -> None:
    """Tarea en segundo plano (BackgroundTasks). Para producción pesada: ARQ + Redis."""
    with SessionLocal() as db:
        pkg = db.get(Package, package_id)
        if pkg is None:
            return
        tenant = db.get(Tenant, pkg.tenant_id)
        if tenant is None:
            return
        send_arrival(db, pkg, tenant)


def dispatch_due_scheduled_qrs(now_utc: datetime | None = None) -> int:
    """Emite y envía el QR de un solo uso para los paquetes cuya ventana (10 min antes) ya llegó."""
    from app.modules.qr import service as qr_service  # import tardío para evitar ciclos

    now = now_utc or utcnow()
    dispatched = 0
    with SessionLocal() as db:
        due_ids = db.scalars(
            select(Package.id).where(
                Package.state.in_(pkgs.OPEN_STATES),
                Package.scheduled_qr_send_at.is_not(None),
                Package.scheduled_qr_send_at <= now,
                Package.scheduled_qr_sent_at.is_(None),
            )
        ).all()

    for pkg_id in due_ids:
        with SessionLocal() as db:
            claimed = db.execute(
                update(Package)
                .where(
                    Package.id == pkg_id,
                    Package.state.in_(pkgs.OPEN_STATES),
                    Package.scheduled_qr_sent_at.is_(None),
                )
                .values(scheduled_qr_sent_at=now)
                .returning(Package.id)
            ).first()
            if claimed is None:
                db.rollback()
                continue
            db.commit()

            pkg = db.get(Package, pkg_id)
            tenant = db.get(Tenant, pkg.tenant_id) if pkg else None
            if pkg is None or tenant is None:
                continue
            try:
                token, expires = qr_service.issue_token(db, tenant, pkg, None)
                send_qr_to_buyer(db, pkg, tenant, None, token, expires)
                dispatched += 1
            except Exception as exc:
                log.exception("Error enviando QR programado para paquete %s: %s", pkg_id, str(exc)[:200])
    return dispatched


def send_pickup_ready_task(
    package_id: int,
    user_id: int | None = None,
    token: str | None = None,
    expires_at: datetime | None = None,
) -> None:
    """Tarea en segundo plano para aviso proactivo de retiro (estado notificable o emisión de QR)."""
    with SessionLocal() as db:
        pkg = db.get(Package, package_id)
        if pkg is None or pkg.state in ("ENTREGADO", "DEVUELTO", "VENCIDO"):
            return
        tenant = db.get(Tenant, pkg.tenant_id)
        if tenant is None:
            return
        send_pickup_ready(db, pkg, tenant, user_id, token=token, expires_at=expires_at)
