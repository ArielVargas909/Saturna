import re
from datetime import datetime, timedelta, timezone

BO_OFFSET = timedelta(hours=-4)  # Bolivia (UTC-4, sin horario de verano)
_WEEKDAYS = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "miércoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "sábado": 5,
    "domingo": 6,
}


def utcnow() -> datetime:
    """UTC ingenuo (sin tzinfo): se guarda igual en PostgreSQL y SQLite."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_local(dt: datetime) -> datetime:
    return dt + BO_OFFSET


def today_start_utc() -> datetime:
    """Inicio del día actual en Bolivia, expresado en UTC ingenuo."""
    local = to_local(utcnow())
    return local.replace(hour=0, minute=0, second=0, microsecond=0) - BO_OFFSET


def _parse_clock(text: str) -> tuple[int, int] | None:
    """Extrae (hora_24h, minuto) desde expresiones como '17:00', '5 pm', '3:15 pm', 'a las 16'."""
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?\s*m\.?|p\.?\s*m\.?)\b", text, re.I)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = m.group(3).lower().replace(".", "").replace(" ", "")
        if 1 <= hour <= 12 and 0 <= minute <= 59:
            if ampm == "pm" and hour != 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
            return hour, minute

    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text)
    if m:
        return int(m.group(1)), int(m.group(2))

    m = re.search(r"\b(?:a\s+las\s+|las\s+)(\d{1,2})(?:\s*(?:hrs?|horas?))?\b", text, re.I)
    if m:
        hour = int(m.group(1))
        if 0 <= hour <= 23:
            if 1 <= hour <= 7 and re.search(r"tarde|noche", text, re.I):
                hour += 12
            return hour, 0

    m = re.search(r"\b(\d{1,2})\s*(?:hrs?|horas?)\b", text, re.I)
    if m:
        hour = int(m.group(1))
        if 0 <= hour <= 23:
            return hour, 0
    return None


def parse_pickup_datetime_utc(
    horario: str,
    *,
    iso_hint: str = "",
    now_utc: datetime | None = None,
) -> datetime | None:
    """Interpreta una hora/fecha acordada en hora de Bolivia (UTC-4) y devuelve UTC ingenuo."""
    now = now_utc or utcnow()
    local_now = to_local(now)

    # 1. Formato ISO opcional provisto por el LLM (en hora local de Bolivia)
    hint = (iso_hint or "").strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"):
        if hint:
            try:
                return datetime.strptime(hint[:19], fmt) - BO_OFFSET
            except ValueError:
                pass

    text = (horario or "").strip()
    if not text:
        return None
    low = text.lower()

    # 2. Expresiones relativas inmediatas: "en 10 minutos", "en 1 hora"
    rel_min = re.search(r"\ben\s+(\d{1,3})\s*(?:min(?:utos?)?)\b", low)
    if rel_min:
        return now + timedelta(minutes=int(rel_min.group(1)))
    rel_hr = re.search(r"\ben\s+(\d{1,2})\s*(?:h(?:oras?)?|hrs?)\b", low)
    if rel_hr:
        return now + timedelta(hours=int(rel_hr.group(1)))

    clock = _parse_clock(low)
    if clock is None:
        return None
    hour, minute = clock

    # 3. Fecha explícita YYYY-MM-DD o DD/MM(/YYYY)
    iso_date = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", low)
    if iso_date:
        try:
            target = datetime(int(iso_date.group(1)), int(iso_date.group(2)), int(iso_date.group(3)), hour, minute)
            return target - BO_OFFSET
        except ValueError:
            return None

    dmy = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", low)
    if dmy:
        day, month = int(dmy.group(1)), int(dmy.group(2))
        year = int(dmy.group(3)) if dmy.group(3) else local_now.year
        if year < 100:
            year += 2000
        try:
            target = datetime(year, month, day, hour, minute)
            return target - BO_OFFSET
        except ValueError:
            return None

    # 4. Días relativos o días de la semana en español
    base_date = local_now.date()
    explicit_day = False
    if "pasado mañana" in low or "pasado manana" in low:
        base_date = base_date + timedelta(days=2)
        explicit_day = True
    elif "mañana" in low or "manana" in low:
        base_date = base_date + timedelta(days=1)
        explicit_day = True
    elif "hoy" in low:
        explicit_day = True
    else:
        for name, wd in _WEEKDAYS.items():
            if re.search(rf"\b{name}\b", low):
                delta = (wd - local_now.weekday()) % 7
                if delta == 0 and (hour, minute) <= (local_now.hour, local_now.minute):
                    delta = 7
                base_date = base_date + timedelta(days=delta)
                explicit_day = True
                break

    target_local = datetime(base_date.year, base_date.month, base_date.day, hour, minute)
    # Si solo dijo una hora (sin "hoy") y ya pasó hace más de 5 minutos, se asume el día siguiente.
    if not explicit_day and target_local < local_now - timedelta(minutes=5):
        target_local = target_local + timedelta(days=1)
    return target_local - BO_OFFSET
