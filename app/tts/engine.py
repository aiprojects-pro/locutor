"""Motor TTS multivoz basado en sherpa-onnx OfflineTts.

- Catálogo de voces definido en config/voices.yaml. Cada voz apunta a una carpeta
  de modelo y a un locutor (sid). Varias voces pueden compartir el mismo modelo
  (p. ej. Sharvard tiene un locutor femenino y otro masculino).
- Cada MODELO se carga UNA sola vez en un pool de instancias OfflineTts
  (tamaño = concurrency) y se hace warm-up. Las voces que comparten modelo
  comparten el pool.
- Campos usados de la API de sherpa-onnx: model, tokens, data_dir, num_threads,
  provider (verificados por introspección en la versión 1.13).
"""

from __future__ import annotations

import glob
import queue
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sherpa_onnx
import yaml

from app.config import Settings
from app.logging_conf import get_logger

logger = get_logger("locutor.engine")


@dataclass
class Voice:
    key: str
    label: str
    model_dir: Path
    sid: int


class _Model:
    """Un modelo cargado: pool de instancias + metadatos."""

    def __init__(self) -> None:
        self.pool: queue.Queue[sherpa_onnx.OfflineTts] = queue.Queue()
        self.sample_rate: int = 0
        self.num_speakers: int = 0


def _build_config(model_dir: Path, num_threads: int, provider: str) -> sherpa_onnx.OfflineTtsConfig:
    onnx = sorted(glob.glob(str(model_dir / "*.onnx")))
    if not onnx:
        raise FileNotFoundError(f"No se encontró ningún .onnx en {model_dir}")
    tokens = model_dir / "tokens.txt"
    if not tokens.exists():
        raise FileNotFoundError(f"No se encontró tokens.txt en {model_dir}")
    vits_kwargs = {"model": onnx[0], "tokens": str(tokens)}
    espeak = model_dir / "espeak-ng-data"
    if espeak.is_dir():  # las voces Piper necesitan estos datos
        vits_kwargs["data_dir"] = str(espeak)
    vits = sherpa_onnx.OfflineTtsVitsModelConfig(**vits_kwargs)
    model = sherpa_onnx.OfflineTtsModelConfig(
        vits=vits, num_threads=num_threads, provider=provider, debug=False
    )
    config = sherpa_onnx.OfflineTtsConfig(model=model)
    if not config.validate():
        raise ValueError(f"Configuración de TTS inválida para {model_dir}")
    return config


class VoiceRegistry:
    """Registro de voces y modelos. Interfaz usada por jobs y la API."""

    def __init__(self, settings: Settings, voices: list[Voice], default_key: str | None):
        if not voices:
            raise ValueError("No hay voces configuradas en voices.yaml")
        self.settings = settings
        self.voices: dict[str, Voice] = {v.key: v for v in voices}
        self.default_key = default_key if default_key in self.voices else voices[0].key
        self._models: dict[str, _Model] = {}
        self._model_locks: dict[str, threading.Lock] = {}
        self._registry_lock = threading.Lock()
        self._loaded = False

    def load(self) -> None:
        """Carga (y calienta) todos los modelos distintos del catálogo."""
        seen: set[str] = set()
        for voice in self.voices.values():
            mkey = str(voice.model_dir)
            if mkey not in seen:
                seen.add(mkey)
                self._ensure_model(voice.model_dir)
        self._loaded = True
        logger.info(
            "voces cargadas",
            extra={"event": "voices_loaded",
                   "status": f"{len(self.voices)} voces / {len(self._models)} modelos / "
                             f"default={self.default_key}"},
        )

    def _ensure_model(self, model_dir: Path) -> _Model:
        key = str(model_dir)
        model = self._models.get(key)
        if model is not None:
            return model
        with self._registry_lock:
            lock = self._model_locks.setdefault(key, threading.Lock())
        with lock:
            model = self._models.get(key)
            if model is not None:
                return model
            config = _build_config(model_dir, self.settings.num_threads, self.settings.provider)
            model = _Model()
            for _ in range(max(1, self.settings.concurrency)):
                model.pool.put(sherpa_onnx.OfflineTts(config))
            first = model.pool.queue[0]
            model.sample_rate = first.sample_rate
            model.num_speakers = first.num_speakers
            # warm-up
            tts = model.pool.get()
            try:
                tts.generate("Hola.", sid=0, speed=1.0)
            finally:
                model.pool.put(tts)
            self._models[key] = model
            logger.info(
                "modelo cargado",
                extra={"event": "model_loaded",
                       "status": f"{model_dir.name} sr={model.sample_rate} "
                                 f"speakers={model.num_speakers}"},
            )
            return model

    @property
    def loaded(self) -> bool:
        return self._loaded

    def list_voices(self) -> list[dict]:
        return [
            {"key": v.key, "label": v.label, "default": v.key == self.default_key}
            for v in self.voices.values()
        ]

    def resolve(self, voice_key: str | None) -> Voice:
        if voice_key and voice_key in self.voices:
            return self.voices[voice_key]
        return self.voices[self.default_key]

    def sample_rate_for(self, voice_key: str | None) -> int:
        voice = self.resolve(voice_key)
        return self._ensure_model(voice.model_dir).sample_rate

    def generate(self, voice_key: str | None, text: str, speed: float) -> np.ndarray:
        """Genera audio (float32) con la voz indicada. Bloqueante: usar en threadpool."""
        voice = self.resolve(voice_key)
        model = self._ensure_model(voice.model_dir)
        tts = model.pool.get()
        try:
            audio = tts.generate(text, sid=voice.sid, speed=speed)
            return np.asarray(audio.samples, dtype=np.float32)
        finally:
            model.pool.put(tts)


def load_voices(settings: Settings) -> tuple[list[Voice], str | None]:
    """Lee config/voices.yaml y devuelve (voces, clave_por_defecto)."""
    path = Path(settings.voices_config)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    default = data.get("default")
    voices: list[Voice] = []
    for item in data.get("voices", []) or []:
        voices.append(Voice(
            key=item["key"],
            label=item.get("label", item["key"]),
            model_dir=settings.models_root / item["model_dir"],
            sid=int(item.get("sid", 0)),
        ))
    return voices, default
