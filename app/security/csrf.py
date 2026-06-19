"""Protección CSRF mediante "double submit cookie" firmada.

Se emite un token CSRF en una cookie firmada y se renderiza el mismo valor en
un campo oculto del formulario. En cada POST se exige que ambos coincidan.
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeSerializer

from app.config import get_settings

_settings = get_settings()
_serializer = URLSafeSerializer(_settings.secret_key, salt="locutor-csrf")


def issue_csrf_token() -> str:
    """Genera un token CSRF firmado para incrustar en cookie y formulario."""
    return _serializer.dumps(secrets.token_urlsafe(32))


def _unwrap(token: str) -> str | None:
    try:
        return _serializer.loads(token)
    except BadSignature:
        return None


def get_or_create_csrf(request: Request) -> str:
    """Devuelve el token de la cookie si es válido; si no, crea uno nuevo."""
    existing = request.cookies.get(_settings.csrf_cookie_name)
    if existing and _unwrap(existing) is not None:
        return existing
    return issue_csrf_token()


def verify_csrf(request: Request, form_token: str | None) -> None:
    """Valida el token CSRF del formulario contra la cookie. Lanza 403 si falla."""
    cookie_token = request.cookies.get(_settings.csrf_cookie_name)
    if not cookie_token or not form_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token CSRF ausente.")
    cv = _unwrap(cookie_token)
    fv = _unwrap(form_token)
    if cv is None or fv is None or not secrets.compare_digest(cv, fv):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token CSRF inválido.")
