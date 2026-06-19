"""Configuración centralizada (variables de entorno + archivo .env).

Toda la configuración sensible (secretos) se toma de variables de entorno y
NUNCA se registra en los logs. Ver ``.env.example`` para la lista completa.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del proyecto (carpeta que contiene este paquete `app`).
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Secretos (obligatorios en producción) ---------------------------
    # Clave para firmar cookies de sesión y tokens CSRF. Generar con:
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    secret_key: str = Field(
        default="CHANGE-ME-dev-only-not-secure",
        description="Clave de firma de sesiones/CSRF. Cambiar en producción.",
    )
    # Token para la API máquina-a-máquina (Authorization: Bearer <token>).
    api_bearer_token: str = Field(
        default="",
        description="Si está vacío, el endpoint /api/tts queda deshabilitado.",
    )

    # --- Voces sherpa-onnx (multivoz) ------------------------------------
    # Carpeta raíz donde viven los modelos descargados.
    models_root: Path = BASE_DIR / "models"
    # Catálogo de voces seleccionables (clave, etiqueta, model_dir, sid).
    voices_config: Path = BASE_DIR / "config" / "voices.yaml"
    # Proveedor de ejecución de onnxruntime: "cpu" o "coreml".
    # ⚠️ Debe medirse (benchmark), no asumirse. Ver README.
    provider: str = "cpu"

    # --- Concurrencia / rendimiento --------------------------------------
    # Hilos por generación (sherpa-onnx OfflineTtsModelConfig.num_threads).
    num_threads: int = 4
    # Generaciones simultáneas. Regla: num_threads * concurrency <= núcleos P.
    # M4 Max (~10 núcleos de rendimiento): 4 * 2 = 8 <= 10.
    concurrency: int = 2
    # Trabajos (documentos) procesados en paralelo.
    max_concurrent_jobs: int = 2
    # Tamaño máximo de cada fragmento (chunk) en caracteres. Acota el trabajo
    # real de cada generate() nativo (un timeout NO puede cancelarlo).
    chunk_max_chars: int = 500
    # Timeout por fragmento (segundos). Solo devuelve error al cliente; el
    # trabajo nativo sigue hasta acabar, por eso se acota con chunk_max_chars.
    per_chunk_timeout_s: float = 60.0

    # --- Límites de entrada ----------------------------------------------
    max_input_chars: int = 50_000
    max_upload_bytes: int = 20 * 1024 * 1024  # 20 MB por archivo
    max_total_upload_bytes: int = 60 * 1024 * 1024  # 60 MB en total
    max_files_per_request: int = 10
    allowed_extensions: tuple[str, ...] = (".pdf", ".docx")

    # --- Audio -----------------------------------------------------------
    default_sid: int = 0
    default_speed: float = 1.0
    silence_ms: int = 120  # silencio entre fragmentos (evita "clicks")
    mp3_bitrate: str = "128k"

    # --- Sesión / cookies ------------------------------------------------
    session_cookie_name: str = "locutor_session"
    csrf_cookie_name: str = "locutor_csrf"
    session_max_age_s: int = 8 * 60 * 60  # 8 horas
    # En producción (HTTPS) DEBE ser True. Solo poner False para http local.
    cookie_secure: bool = True

    # --- Rate limiting / anti fuerza bruta -------------------------------
    login_max_attempts: int = 5           # intentos antes de bloquear
    login_lockout_seconds: int = 900      # 15 min de bloqueo de cuenta
    login_window_seconds: int = 900       # ventana para contar intentos por IP
    login_ip_max_attempts: int = 20       # intentos por IP en la ventana
    tts_jobs_per_minute: int = 6          # trabajos TTS por usuario/min

    # --- Red / proxy -----------------------------------------------------
    # Solo si hay un reverse proxy de confianza delante (Caddy/nginx) que
    # establece X-Forwarded-For. Si es False, se usa la IP del socket.
    trust_proxy: bool = False
    # Whitelist de IPs para la API. Vacío = desactivado (acceso público).
    api_ip_whitelist: tuple[str, ...] = ()

    # --- Rutas de datos --------------------------------------------------
    db_url: str = f"sqlite:///{BASE_DIR / 'data' / 'locutor.db'}"
    work_dir: Path = BASE_DIR / "data" / "jobs"
    normalization_config: Path = BASE_DIR / "config" / "normalization.yaml"
    job_ttl_seconds: int = 24 * 60 * 60  # borrar audios de trabajos tras 24h

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in {"cpu", "coreml"}:
            raise ValueError("provider debe ser 'cpu' o 'coreml'")
        return v

    @property
    def model_path(self) -> Path:
        return self.model_dir / self.model_filename

    @property
    def tokens_path(self) -> Path:
        return self.model_dir / self.tokens_filename


@lru_cache
def get_settings() -> Settings:
    return Settings()
