import inspect

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.text import title_name
from app.db.session import SessionLocal
from app.models import Notification, Package, Tenant
from app.modules.notifications import whatsapp
from app.modules.packages import service as pkgs
from app.modules.tenants import service as tenants

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


def _qr_png(db: Session, pkg: Package, tenant: Tenant, user_id: int | None) -> bytes:
    """Emite el QR de retiro del paquete y devuelve la imagen PNG."""
    from app.modules.qr import service as qr_service  # import tardío para evitar ciclos

    public = [n for n in dir(qr_service) if not n.startswith("_") and callable(getattr(qr_service, n))]
    issue = next((getattr(qr_service, n) for n in ISSUE_NAMES if hasattr(qr_service, n)), None)
    render = next((getattr(qr_service, n) for n in PNG_NAMES if hasattr(qr_service, n)), None)
    if issue is None or render is None:
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


def send_arrival(db: Session, pkg: Package, tenant: Tenant, user_id: int | None = None) -> Notification:
    """Envía el aviso de llegada respetando el límite mensual del plan."""
    note = Notification(tenant_id=tenant.id, package_id=pkg.id, kind="aviso_llegada", status="queued")
    db.add(note)
    s = get_settings()
    if whatsapp.is_mock():
        note.status = "simulated"
        note.meta_message_id = None
        note.detail = "Sin credenciales de WhatsApp; envío simulado"
        pkgs.add_event(db, pkg.id, "AVISO_SIMULADO", note.detail, user_id)
        db.commit()
        return note
    if tenants.limit_reached(db, tenant, "notifications"):
        note.status, note.detail = "failed", "limite_plan"
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

    real_sent = res.ok and bool(res.message_id) and not res.message_id.startswith("mock-")
    note.status = "sent" if real_sent else "failed"
    note.meta_message_id = res.message_id if real_sent else None
    note.detail = res.detail
    if real_sent:
        tenants.increment(db, tenant.id, "notifications")
        if pkg.state == "REGISTRADO":
            pkgs.change_state(db, pkg, "NOTIFICADO", user_id, "Aviso enviado por WhatsApp")
    else:
        pkgs.add_event(db, pkg.id, "AVISO_FALLIDO", res.detail, user_id)
    db.commit()
    return note


def send_arrival_task(package_id: int) -> None:
    """Tarea en segundo plano (BackgroundTasks). Para producción pesada: ARQ + Redis."""
    with SessionLocal() as db:
        pkg = db.get(Package, package_id)
        if pkg is None:
            return
        tenant = db.get(Tenant, pkg.tenant_id)
        send_arrival(db, pkg, tenant)
