"""Limitador en memoria (ventana deslizante). Para varias instancias usar Redis."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException

_hits: dict[str, deque] = defaultdict(deque)


def check_rate(key: str, limit: int, window: int = 60) -> None:
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Demasiados intentos. Espera un momento.")
    q.append(now)


def reset_rate_limits() -> None:
    _hits.clear()
