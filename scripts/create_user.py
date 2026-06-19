"""CLI para crear/gestionar usuarios.

El registro abierto está deshabilitado por diseño: los usuarios se crean aquí.

Uso:
    python -m scripts.create_user --username admin --admin
    python -m scripts.create_user --username rosario
    python -m scripts.create_user --username admin --reset-password
"""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from app.db.models import User
from app.db.session import db_session, init_db
from app.security.auth import hash_password


def _read_password() -> str:
    pw1 = getpass.getpass("Contraseña: ")
    if len(pw1) < 10:
        print("La contraseña debe tener al menos 10 caracteres.", file=sys.stderr)
        sys.exit(2)
    pw2 = getpass.getpass("Repite la contraseña: ")
    if pw1 != pw2:
        print("Las contraseñas no coinciden.", file=sys.stderr)
        sys.exit(2)
    return pw1


def main() -> None:
    parser = argparse.ArgumentParser(description="Gestión de usuarios de Locutor")
    parser.add_argument("--username", required=True)
    parser.add_argument("--admin", action="store_true", help="Marcar como administrador")
    parser.add_argument("--reset-password", action="store_true",
                        help="Restablecer la contraseña de un usuario existente")
    args = parser.parse_args()

    init_db()
    username = args.username.strip()

    with db_session() as session:
        existing = session.scalar(select(User).where(User.username == username))
        if existing and not args.reset_password:
            print(f"El usuario '{username}' ya existe. Usa --reset-password.", file=sys.stderr)
            sys.exit(1)
        if not existing and args.reset_password:
            print(f"El usuario '{username}' no existe.", file=sys.stderr)
            sys.exit(1)

        password = _read_password()
        if existing:
            existing.password_hash = hash_password(password)
            existing.failed_attempts = 0
            existing.locked_until = None
            print(f"Contraseña actualizada para '{username}'.")
        else:
            session.add(User(
                username=username,
                password_hash=hash_password(password),
                is_admin=args.admin,
                is_active=True,
            ))
            print(f"Usuario '{username}' creado{' (admin)' if args.admin else ''}.")


if __name__ == "__main__":
    main()
