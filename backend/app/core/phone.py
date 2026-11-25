import re

from app.core.config import get_settings


def normalize_phone(raw: str) -> str:
    """'7xxxxxxx' -> '5917xxxxxxx'. Lanza ValueError si no parece un teléfono."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 8:
        digits = get_settings().default_country_code + digits
    if not 10 <= len(digits) <= 15:
        raise ValueError("Teléfono inválido")
    return digits


def normalize_optional(raw: str | None) -> str | None:
    """Para formularios: vacío -> None; inválido -> HTTP 422."""
    if not raw or not raw.strip():
        return None
    from fastapi import HTTPException

    try:
        return normalize_phone(raw)
    except ValueError:
        raise HTTPException(422, "Teléfono inválido") from None
