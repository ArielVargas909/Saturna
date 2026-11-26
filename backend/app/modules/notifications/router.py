import hashlib
import hmac
import json
import logging
from copy import deepcopy

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.deps import DB, CurrentTenant, CurrentUser
from app.db.session import SessionLocal
from app.models import Notification, ProcessedMessage
from app.modules.ai_agent import service as agent
from app.modules.notifications import service, whatsapp
from app.modules.packages import service as pkgs

router = APIRouter(tags=["notifications"])
log = logging.getLogger("saturna.webhook")


@router.get("/notifications")
def list_notifications(db: DB, tenant: CurrentTenant, limit: int = 50):
    rows = db.scalars(
        select(Notification)
        .where(Notification.tenant_id == tenant.id)
        .order_by(Notification.id.desc())
        .limit(min(limit, 200))
    ).all()
    return [
        {"id": n.id, "package_id": n.package_id, "kind": n.kind, "status": n.status,
         "detail": n.detail, "created_at": n.created_at}
        for n in rows
    ]


@router.post("/packages/{package_id}/notify")
def resend(package_id: int, db: DB, tenant: CurrentTenant, user: CurrentUser):
    pkg = pkgs.get_owned(db, tenant.id, package_id)
    if pkg.state in ("ENTREGADO", "DEVUELTO"):
        raise HTTPException(409, "El paquete ya está cerrado")
    n = service.send_arrival(db, pkg, tenant, user.id)
    if n.status == "simulated":
        raise HTTPException(202, "Aviso simulado: configure WhatsApp para enviar el mensaje")
    if n.status == "failed":
        raise HTTPException(502, f"No se pudo enviar el aviso: {n.detail}")
    return {"status": n.status, "detail": n.detail}


# ---------------- Webhook de Meta ----------------
@router.get("/webhooks/whatsapp")
def verify(
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
):
    if mode == "subscribe" and hmac.compare_digest(token, get_settings().whatsapp_verify_token):
        return Response(challenge, media_type="text/plain")
    raise HTTPException(403, "Token de verificación inválido")


def _valid_signature(body: bytes, header: str | None) -> bool:
    secret = get_settings().whatsapp_app_secret
    if not secret:
        if get_settings().environment == "development":
            log.warning("WHATSAPP_APP_SECRET vacío: la firma del webhook no se verificará")
            return True
        log.error("Configuración inválida: WHATSAPP_APP_SECRET vacío")
        return False
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def _log_reply_notification(
    tenant_id: int | None,
    package_id: int | None,
    kind: str,
    res: whatsapp.SendResult,
    preview: str,
) -> None:
    if tenant_id is None:
        return
    status = "simulated" if res.simulated else ("sent" if res.ok else "failed")
    meta_id = None if (res.simulated or not res.ok or res.message_id.startswith("mock-")) else res.message_id
    detail = (res.detail or preview)[:240]
    with SessionLocal() as db:
        db.add(
            Notification(
                tenant_id=tenant_id,
                package_id=package_id,
                kind=kind,
                status=status,
                meta_message_id=meta_id,
                detail=detail,
            )
        )
        db.commit()


def process_incoming(payload: dict) -> None:
    s = get_settings()
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if "messages" not in value:
                continue
            for msg in value.get("messages", []):
                phone = msg.get("from", "")
                msg_type = msg.get("type")
                if msg_type == "text":
                    text = msg.get("text", {}).get("body", "")
                else:  # audios, imágenes y eventos de estado quedan fuera del MVP
                    log.info("Mensaje WhatsApp ignorado por tipo=%s", msg_type)
                    continue
                if not text:
                    continue
                try:
                    with SessionLocal() as db:
                        result = agent.handle_message(db, phone, text)
                    fallback_params = result.get("fallback_params")
                    fallback_tpl = s.whatsapp_template_arrival if fallback_params else None
                    text_res = whatsapp.send_text(
                        phone,
                        result["reply"],
                        fallback_template=fallback_tpl,
                        fallback_params=fallback_params,
                    )
                    _log_reply_notification(
                        result.get("tenant_id"),
                        result.get("package_id"),
                        "respuesta_ia",
                        text_res,
                        result["reply"],
                    )
                    for item in result["outbox"]:
                        if item["type"] == "image":
                            img_res = whatsapp.send_image(
                                phone,
                                item["url"],
                                item.get("caption", ""),
                                fallback_template=fallback_tpl,
                                fallback_params=fallback_params,
                            )
                            _log_reply_notification(
                                result.get("tenant_id"),
                                result.get("package_id"),
                                "qr_retiro",
                                img_res,
                                item.get("caption", "QR de retiro"),
                            )
                        elif (
                            item["type"] == "location"
                            and item.get("latitude") is not None
                            and item.get("longitude") is not None
                        ):
                            loc_res = whatsapp.send_location(
                                phone,
                                float(item["latitude"]),
                                float(item["longitude"]),
                                item.get("name", ""),
                                item.get("address", ""),
                                fallback_template=fallback_tpl,
                                fallback_params=fallback_params,
                            )
                            _log_reply_notification(
                                result.get("tenant_id"),
                                result.get("package_id"),
                                "ubicacion",
                                loc_res,
                                item.get("address") or item.get("name") or "Ubicación de paquetería",
                            )
                except Exception as exc:
                    log.exception("Error procesando mensaje entrante de WhatsApp: %s", str(exc)[:300])


def reserve_text_messages(payload: dict) -> dict:
    """Reserva los IDs nuevos antes de programar el procesamiento en segundo plano."""
    filtered = deepcopy(payload)
    filtered["entry"] = []
    with SessionLocal() as db:
        for entry in payload.get("entry", []):
            filtered_entry = deepcopy(entry)
            filtered_changes = []
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if "messages" not in value:
                    continue
                filtered_messages = []
                for msg in value.get("messages", []):
                    if msg.get("type") != "text":
                        continue
                    message_id = msg.get("id")
                    if not message_id:
                        continue
                    db.add(ProcessedMessage(message_id=str(message_id)))
                    try:
                        db.commit()
                    except IntegrityError:
                        db.rollback()
                        continue
                    filtered_messages.append(deepcopy(msg))
                if filtered_messages:
                    filtered_change = deepcopy(change)
                    filtered_change["value"] = deepcopy(value)
                    filtered_change["value"]["messages"] = filtered_messages
                    filtered_changes.append(filtered_change)
            if filtered_changes:
                filtered_entry["changes"] = filtered_changes
                filtered["entry"].append(filtered_entry)
        db.commit()
    return filtered


@router.post("/webhooks/whatsapp")
async def incoming(request: Request, bg: BackgroundTasks):
    body = await request.body()
    if not _valid_signature(body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(403, "Firma inválida")
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400, "JSON inválido") from None
    unique_payload = reserve_text_messages(payload)
    if unique_payload["entry"]:
        bg.add_task(process_incoming, unique_payload)
    return {"ok": True}
