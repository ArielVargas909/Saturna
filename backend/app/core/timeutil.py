from datetime import datetime, timedelta, timezone

BO_OFFSET = timedelta(hours=-4)  # Bolivia (UTC-4, sin horario de verano)


def utcnow() -> datetime:
    """UTC ingenuo (sin tzinfo): se guarda igual en PostgreSQL y SQLite."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_local(dt: datetime) -> datetime:
    return dt + BO_OFFSET


def today_start_utc() -> datetime:
    """Inicio del día actual en Bolivia, expresado en UTC ingenuo."""
    local = to_local(utcnow())
    return local.replace(hour=0, minute=0, second=0, microsecond=0) - BO_OFFSET
