"""Rate limiting en memoria (proceso único).

- Ventana fija por clave (IP o usuario).
- Pensado para un solo proceso uvicorn; el estado es global en memoria.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.config import get_settings

_settings = get_settings()


class FixedWindowLimiter:
    """Limita a `max_events` por `window_seconds` y por clave."""

    def __init__(self, max_events: int, window_seconds: float):
        self.max_events = max_events
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Registra un evento. Devuelve True si está permitido, False si excede."""
        now = time.monotonic()
        with self._lock:
            dq = self._events[key]
            while dq and now - dq[0] > self.window:
                dq.popleft()
            if len(dq) >= self.max_events:
                return False
            dq.append(now)
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


# Limitadores globales del proceso.
login_ip_limiter = FixedWindowLimiter(
    _settings.login_ip_max_attempts, _settings.login_window_seconds
)
tts_user_limiter = FixedWindowLimiter(_settings.tts_jobs_per_minute, 60.0)


def client_ip(request: Request) -> str:
    """IP del cliente. Solo confía en X-Forwarded-For si TRUST_PROXY está activo."""
    if _settings.trust_proxy:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            # Primera IP de la cadena = cliente original.
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
