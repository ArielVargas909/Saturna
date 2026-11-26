"""Cliente de WhatsApp Cloud API. Sin WHATSAPP_TOKEN funciona en modo simulado (solo registra)."""

import logging
import time
import uuid
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

log = logging.getLogger("saturna.whatsapp")
SENT_LOG: list[dict] = []  # bitácora en memoria del modo simulado (útil en desarrollo y pruebas)
OUTSIDE_WINDOW_CODES = {131047}  # Meta Cloud API: ventana de atención de 24 h expirada


@dataclass
class SendResult:
    ok: bool
    message_id: str = ""
    detail: str = ""
    simulated: bool = False
    error_code: int | None = None
    outside_window: bool = False
    fallback_used: bool = False


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
    return SendResult(True, "mock-" + uuid.uuid4().hex[:12], detail="Envío simulado", simulated=True)


def _parse_meta_error(response: httpx.Response) -> tuple[int | None, str]:
    try:
        data = response.json()
    except ValueError:
        return None, f"HTTP {response.status_code}: {response.text[:150]}"
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        code = err.get("code")
        code_int = int(code) if isinstance(code, int) or (isinstance(code, str) and code.isdigit()) else None
        msg = str(err.get("message") or response.text[:150])[:150]
        if code_int:
            return code_int, f"HTTP {response.status_code} ({code_int}): {msg}"
        return None, f"HTTP {response.status_code}: {msg}"
    return None, f"HTTP {response.status_code}: {response.text[:150]}"


def _post(payload: dict) -> SendResult:
    s = get_settings()
    url = f"https://graph.facebook.com/{s.whatsapp_graph_version}/{s.whatsapp_phone_id}/messages"
    headers = {"Authorization": f"Bearer {s.whatsapp_token}"}
    last = "sin respuesta"
    last_code: int | None = None
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
                message_id = (
                    messages[0].get("id")
                    if (isinstance(messages, list) and messages and isinstance(messages[0], dict))
                    else None
                )
                if message_id:
                    log.info("WhatsApp status=%s message_id=%s", r.status_code, message_id)
                    return SendResult(True, str(message_id))
                log.error("WhatsApp status=%s cuerpo=%s", r.status_code, body)
                return SendResult(False, detail="Meta respondió 2xx sin message id")
            last_code, last = _parse_meta_error(r)
            log.error("WhatsApp status=%s code=%s cuerpo=%s", r.status_code, last_code, body)
            if r.status_code < 500:  # error del cliente: no tiene sentido reintentar
                break
        except httpx.HTTPError as exc:
            last = str(exc)[:150]
            log.error("WhatsApp fallo=%s", last)
        time.sleep(0.25)
    return SendResult(
        False,
        detail=last,
        error_code=last_code,
        outside_window=last_code in OUTSIDE_WINDOW_CODES,
    )


def _fallback_to_template(
    to: str,
    original: SendResult,
    fallback_template: str | None,
    fallback_params: list[str] | None,
) -> SendResult:
    if original.ok or not original.outside_window or not fallback_template:
        return original
    log.warning(
        "WhatsApp fuera de ventana 24h (code=%s) para %s; usando plantilla %s",
        original.error_code,
        mask_phone(to),
        fallback_template,
    )
    fb = send_template(to, fallback_template, fallback_params or [])
    fb.fallback_used = True
    fb.outside_window = True
    fb.error_code = original.error_code
    if fb.ok:
        fb.detail = f"Fuera de ventana 24h; enviado con plantilla '{fallback_template}'"
    else:
        fb.detail = f"Fuera de ventana 24h; fallback con plantilla falló: {fb.detail}"
    return fb


def send_text(
    to: str,
    text: str,
    *,
    fallback_template: str | None = None,
    fallback_params: list[str] | None = None,
) -> SendResult:
    """Envía un mensaje de texto libre (con fallback a plantilla si expiró la ventana de 24 h)."""
    if is_mock():
        return _record({"type": "text", "to": to, "text": text})
    res = _post(
        {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
    )
    return _fallback_to_template(to, res, fallback_template, fallback_params)


def send_image(
    to: str,
    image_url: str,
    caption: str = "",
    *,
    fallback_template: str | None = None,
    fallback_params: list[str] | None = None,
) -> SendResult:
    """Envía una imagen por URL pública (con fallback a plantilla si expiró la ventana de 24 h)."""
    if is_mock():
        return _record({"type": "image", "to": to, "url": image_url, "caption": caption})
    image_payload: dict[str, str] = {"link": image_url}
    if caption:
        image_payload["caption"] = caption
    res = _post(
        {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "image",
            "image": image_payload,
        }
    )
    return _fallback_to_template(to, res, fallback_template, fallback_params)


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
        code, detail = _parse_meta_error(r)
        return SendResult(False, detail=detail, error_code=code)
    except httpx.HTTPError as exc:
        log.error("WhatsApp media fallo=%s", str(exc)[:150])
        return SendResult(False, detail=str(exc)[:150])
