"""API máquina-a-máquina: /health y /api/tts (Authorization: Bearer).

- Whitelist por IP del socket (configurable; vacío = desactivado).
- Secreto comparado con hmac.compare_digest. Nunca se registra.
- Devuelve audio sin pérdidas (WAV PCM_16) con el sample rate en una cabecera.
"""

from __future__ import annotations

import hmac
import io

import numpy as np
import soundfile as sf
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.config import get_settings
from app.security.ratelimit import client_ip
from app.tts.audio import merge_with_silence
from app.tts.chunk import chunk_text

router = APIRouter()
_settings = get_settings()


class TtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=_settings.max_input_chars)
    voice: str | None = Field(default=None, description="Clave de voz (ver /voices). Vacío = voz por defecto.")
    speed: float = Field(default=_settings.default_speed, gt=0.1, le=3.0)


def require_api_auth(request: Request) -> None:
    """Valida IP whitelist (si está activa) y el token Bearer."""
    if not _settings.api_bearer_token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "API deshabilitada.")

    # 1) Whitelist por IP (de la IP del socket, salvo TRUST_PROXY).
    if _settings.api_ip_whitelist:
        ip = client_ip(request)
        if ip not in _settings.api_ip_whitelist:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "IP no autorizada.")

    # 2) Token Bearer (comparación en tiempo constante).
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Falta el token Bearer.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not hmac.compare_digest(token, _settings.api_bearer_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido.")


@router.get("/health")
def health(request: Request) -> dict:
    engine = request.app.state.engine
    return {
        "status": "ok" if engine.loaded else "starting",
        "model_loaded": engine.loaded,
        "voices": len(engine.voices),
    }


@router.get("/voices")
def list_voices(request: Request) -> dict:
    return {"voices": request.app.state.engine.list_voices()}


@router.post("/api/tts", dependencies=[Depends(require_api_auth)])
async def api_tts(payload: TtsRequest, request: Request) -> Response:
    engine = request.app.state.engine
    normalizer = request.app.state.normalizer
    settings = request.app.state.settings

    normalized = normalizer.normalize(payload.text)
    chunks = chunk_text(normalized, settings.chunk_max_chars)
    if not chunks:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Texto vacío tras normalizar.")

    sample_rate = engine.sample_rate_for(payload.voice)

    def _synthesize() -> np.ndarray:
        parts = [engine.generate(payload.voice, c, payload.speed) for c in chunks]
        return merge_with_silence(parts, sample_rate, settings.silence_ms)

    samples = await run_in_threadpool(_synthesize)

    buf = io.BytesIO()
    sf.write(buf, samples, samplerate=sample_rate, format="WAV", subtype="PCM_16")
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="audio/wav",
        headers={
            "X-Sample-Rate": str(sample_rate),
            "Content-Disposition": 'attachment; filename="tts.wav"',
        },
    )
