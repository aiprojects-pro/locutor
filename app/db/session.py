"""Conexión a la base de datos (SQLite + SQLAlchemy 2.0)."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Base

_settings = get_settings()

# check_same_thread=False porque usamos la sesión desde hilos del threadpool.
_engine = create_engine(
    _settings.db_url,
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Crea las tablas y la carpeta de datos si no existen."""
    db_path = _settings.db_url.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(_engine)


@contextmanager
def db_session():
    """Context manager que abre y cierra una sesión de forma segura."""
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
