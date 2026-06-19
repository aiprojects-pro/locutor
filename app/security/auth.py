"""Autenticación: hashing Argon2, sesiones por cookie firmada y login.

- Contraseñas con Argon2 (argon2-cffi).
- Sesión en cookie firmada con itsdangerous (HttpOnly, Secure, SameSite).
- Bloqueo de cuenta tras N intentos fallidos.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select

from app.config import get_settings
from app.db.models import User
from app.db.session import db_session

_settings = get_settings()
_ph = PasswordHasher()
_serializer = URLSafeTimedSerializer(_settings.secret_key, salt="locutor-session")


# --- Hashing de contraseñas ---------------------------------------------

def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        _ph.verify(stored_hash, password)
        return True
    except VerifyMismatchError:
        return False
    except Exception:
        # Hash corrupto o formato inesperado: tratar como fallo de login.
        return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _ph.check_needs_rehash(stored_hash)
    except Exception:
        return False


# --- Sesión por cookie ---------------------------------------------------

def create_session_token(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def read_session_token(token: str) -> int | None:
    try:
        data = _serializer.loads(token, max_age=_settings.session_max_age_s)
        return int(data["uid"])
    except (BadSignature, SignatureExpired, KeyError, ValueError, TypeError):
        return None


def get_current_user(request: Request) -> User | None:
    """Devuelve el usuario autenticado a partir de la cookie, o None."""
    token = request.cookies.get(_settings.session_cookie_name)
    if not token:
        return None
    uid = read_session_token(token)
    if uid is None:
        return None
    with db_session() as session:
        user = session.get(User, uid)
        if user is None or not user.is_active:
            return None
        # Desligar de la sesión para usarlo fuera del context manager.
        session.expunge(user)
        return user


# --- Login con bloqueo de cuenta ----------------------------------------

class LoginResult:
    def __init__(self, user: User | None, error: str | None = None):
        self.user = user
        self.error = error


def authenticate(username: str, password: str) -> LoginResult:
    """Valida credenciales aplicando bloqueo de cuenta. No revela si el
    usuario existe (mensaje genérico) para no facilitar enumeración."""
    now = datetime.now(timezone.utc)
    generic = "Usuario o contraseña incorrectos."
    with db_session() as session:
        user = session.scalar(select(User).where(User.username == username))
        if user is None:
            # Verificación "dummy" para igualar el tiempo de respuesta y evitar
            # ataques de temporización que revelen si el usuario existe.
            _ph.hash("dummy-timing-equalizer")
            return LoginResult(None, generic)

        if user.is_locked():
            return LoginResult(None, "Cuenta bloqueada temporalmente. Inténtalo más tarde.")

        if not user.is_active:
            return LoginResult(None, generic)

        if verify_password(user.password_hash, password):
            user.failed_attempts = 0
            user.locked_until = None
            if needs_rehash(user.password_hash):
                user.password_hash = hash_password(password)
            session.expunge(user)
            return LoginResult(user)

        # Fallo: incrementar contador y bloquear si procede.
        user.failed_attempts += 1
        if user.failed_attempts >= _settings.login_max_attempts:
            user.locked_until = now + timedelta(seconds=_settings.login_lockout_seconds)
            user.failed_attempts = 0
        return LoginResult(None, generic)
