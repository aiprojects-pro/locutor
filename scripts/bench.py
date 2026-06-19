"""Benchmark sencillo del motor TTS para comparar PROVIDER y NUM_THREADS.

Mide el RTF (real-time factor = tiempo_generación / duración_audio): cuanto más
bajo, mejor. Usa la configuración de .env / variables de entorno.

Uso:
    PROVIDER=cpu    NUM_THREADS=4 ./.venv/bin/python -m scripts.bench
    PROVIDER=coreml NUM_THREADS=4 ./.venv/bin/python -m scripts.bench
"""

from __future__ import annotations

import time

from app.config import get_settings
from app.tts.engine import VoiceRegistry, load_voices

TEXT = (
    "Esta es una frase de prueba para medir el rendimiento del motor de "
    "texto a voz en español. Repetimos el contenido varias veces para obtener "
    "una medición estable y representativa del coste de generación."
) * 3


def main() -> None:
    settings = get_settings()
    voices, default = load_voices(settings)
    engine = VoiceRegistry(settings, voices, default)
    print(f"Cargando modelos… provider={settings.provider} num_threads={settings.num_threads} "
          f"voz={engine.default_key}")
    engine.load()  # incluye warm-up
    sr = engine.sample_rate_for(engine.default_key)

    runs = 3
    total_audio_s = 0.0
    total_gen_s = 0.0
    for i in range(runs):
        start = time.perf_counter()
        samples = engine.generate(engine.default_key, TEXT, 1.0)
        elapsed = time.perf_counter() - start
        audio_s = len(samples) / sr
        total_audio_s += audio_s
        total_gen_s += elapsed
        print(f"  run {i + 1}: gen={elapsed:.2f}s  audio={audio_s:.2f}s  RTF={elapsed / audio_s:.3f}")

    print(f"\nRTF medio: {total_gen_s / total_audio_s:.3f} "
          f"(provider={settings.provider}, num_threads={settings.num_threads})")


if __name__ == "__main__":
    main()
