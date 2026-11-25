"""Cliente de WhatsApp Cloud API. Sin WHATSAPP_TOKEN funciona en modo simulado (solo registra)."""

import logging
import time
import uuid
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

log = logging.getLogger("saturna.whatsapp")
SENT_LOG: list[dict] = []  # bitácora en memoria del modo simulado (útil en desarrollo y pruebas)


@dataclass
class SendResult:
    ok: bool
    message_id: str = ""
    detail: str = ""


def mask_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) <= 4:
        return "*" * len(digits)
    return digits[:2] + "*" * (len(digits) - 4) + digits[-2:]


def is_mock() -> bool:
    s = get_settings()
    return not (s.whatsapp_token and s.whatsapp_phone_id)


def _record(entry: dict) -> SendResult:
    SENT_LOG.append(entry)
    del SENT_LOG[:-200]
    logged = dict(entry)
    if "to" in logged:
        logged["to"] = mask_phone(str(logged["to"]))
    log.info("[WhatsApp simulado] %s", logged)
    return SendResult(True, "mock-" + uuid.uuid4().hex[:12])


def _post(payload: dict) -> SendResult:
    s = get_settings()
    url = f"https://graph.facebook.com/{s.whatsapp_graph_version}/{s.whatsapp_phone_id}/messages"
    headers = {"Authorization": f"Bearer {s.whatsapp_token}"}
    last = "sin respuesta"
    for _attempt in range(2):  # Máximo un reintento: 2 intentos x 8 segundos
        try:
            r = httpx.post(url, json=payload, headers=headers, timeout=8)
            body = r.text[:300]
            if 200 <= r.status_code < 300:
                try:
                    response_data = r.json()
                except ValueError:
                    log.error("WhatsApp status=%s respuesta JSON inválida", r.status_code)
                    return SendResult(False, detail="Meta respondió con JSON inválido")
                messages = response_data.get("messages") if isinstance(response_data, dict) else None
                message_id = messages[0].get("id") if (
                    isinstance(messages, list) and messages and isinstance(messages[0], dict)
                ) else None
                if message_id:
                    log.info("WhatsApp status=%s message_id=%s", r.status_code, message_id)
                    return SendResult(True, str(message_id))
                log.error("WhatsApp status=%s cuerpo=%s", r.status_code, body)
                return SendResult(False, detail="Meta respondió 2xx sin message id")
            last = f"HTTP {r.status_code}: {r.text[:150]}"
            log.error("WhatsApp status=%s cuerpo=%s", r.status_code, body)
            if r.status_code < 500:  # error del cliente: no tiene sentido reintentar
                break
        except httpx.HTTPError as exc:
            last = str(exc)[:150]
            log.error("WhatsApp fallo=%s", last)
        time.sleep(0.25)
    return SendResult(False, detail=last)


def send_text(to: str, text: str) -> SendResult:
    """Envía un mensaje de texto libre (dentro de la ventana de 24 h de WhatsApp)."""
    if is_mock():
        return _record({"type": "text", "to": to, "text": text})
    return _post(
        {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
    )


def send_image(to: str, image_url: str, caption: str = "") -> SendResult:
    """Envía una imagen por URL pública (p. ej. el QR de retiro solicitado por el comprador)."""
    if is_mock():
        return _record({"type": "image", "to": to, "url": image_url, "caption": caption})
    image_payload: dict[str, str] = {"link": image_url}
    if caption:
        image_payload["caption"] = caption
    return _post(
        {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "image",
            "image": image_payload,
        }
    )


def send_template(to: str, template: str, params: list[str]) -> SendResult:
    """Envía una plantilla de WhatsApp con variables de texto en el cuerpo."""
    if is_mock():
        return _record({"type": "template", "to": to, "template": template, "params": params})
    s = get_settings()
    return _post(
        {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": s.whatsapp_template_lang},
                "components": [
                    {"type": "body", "parameters": [{"type": "text", "text": p} for p in params]},
                ],
            },
        }
    )


def send_template_image(to: str, template: str, params: list[str], media_id: str) -> SendResult:
    """Plantilla con imagen en el encabezado (el QR) y variables de texto en el cuerpo."""
    if is_mock():
        return _record({"type": "template_image", "to": to, "template": template, "params": params})
    s = get_settings()
    return _post(
        {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": s.whatsapp_template_lang},
                "components": [
                    {"type": "header", "parameters": [{"type": "image", "image": {"id": media_id}}]},
                    {"type": "body", "parameters": [{"type": "text", "text": p} for p in params]},
                ],
            },
        }
    )
def upload_media(png_bytes: bytes) -> SendResult:
    """Sube una imagen PNG a Meta y devuelve su media id (en message_id)."""
    if is_mock():
        return _record({"type": "media_upload", "bytes": len(png_bytes)})
    s = get_settings()
    url = f"https://graph.facebook.com/{s.whatsapp_graph_version}/{s.whatsapp_phone_id}/media"
    headers = {"Authorization": f"Bearer {s.whatsapp_token}"}
    try:
        r = httpx.post(
            url,
            headers=headers,
            data={"messaging_product": "whatsapp", "type": "image/png"},
            files={"file": ("qr.png", png_bytes, "image/png")},
            timeout=15,
        )
        try:
            response_data = r.json()
        except ValueError:
            response_data = None
        if (
            200 <= r.status_code < 300
            and isinstance(response_data, dict)
            and response_data.get("id")
        ):
            return SendResult(True, str(response_data["id"]))
        log.error("WhatsApp media status=%s cuerpo=%s", r.status_code, r.text[:300])
        if 200 <= r.status_code < 300:
            return SendResult(False, detail="Meta respondió 2xx sin media id válido")
        return SendResult(False, detail=f"HTTP {r.status_code}: {r.text[:150]}")
    except httpx.HTTPError as exc:
        log.error("WhatsApp media fallo=%s", str(exc)[:150])
        return SendResult(False, detail=str(exc)[:150])
