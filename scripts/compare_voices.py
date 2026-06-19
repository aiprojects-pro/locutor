"""Genera la MISMA frase con cada voz instalada en models/ para compararlas.

Crea un MP3 por voz en /tmp/voces/. Detecta automáticamente el .onnx, el
tokens.txt y, si existe, la carpeta espeak-ng-data (necesaria para voces Piper).

Uso:  ./.venv/bin/python -m scripts.compare_voices
"""

from __future__ import annotations

import glob
from pathlib import Path

import sherpa_onnx

from app.tts.audio import assemble_mp3

FRASE = (
    "Hola, esta es una prueba de voz para el proyecto Locutor. "
    "El informe del mes asciende a mil novecientos noventa y uno con cincuenta euros. "
    "¿Qué te parece esta voz?"
)

MODELS_DIR = Path("models")
OUT_DIR = Path("/tmp/voces")


def build_config(model_dir: Path) -> sherpa_onnx.OfflineTtsConfig | None:
    onnx = sorted(glob.glob(str(model_dir / "*.onnx")))
    tokens = model_dir / "tokens.txt"
    if not onnx or not tokens.exists():
        return None
    vits_kwargs = {"model": onnx[0], "tokens": str(tokens)}
    espeak = model_dir / "espeak-ng-data"
    if espeak.is_dir():
        vits_kwargs["data_dir"] = str(espeak)
    vits = sherpa_onnx.OfflineTtsVitsModelConfig(**vits_kwargs)
    model = sherpa_onnx.OfflineTtsModelConfig(vits=vits, num_threads=4, provider="cpu")
    config = sherpa_onnx.OfflineTtsConfig(model=model)
    return config if config.validate() else None


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    voices = sorted(p for p in MODELS_DIR.iterdir() if p.is_dir())
    print(f"Voces encontradas: {[v.name for v in voices]}\n")
    for vdir in voices:
        config = build_config(vdir)
        if config is None:
            print(f"  ✗ {vdir.name}: no es un modelo válido, omitido")
            continue
        tts = sherpa_onnx.OfflineTts(config)
        audio = tts.generate(FRASE, sid=0, speed=1.0)
        import numpy as np
        samples = np.asarray(audio.samples, dtype=np.float32)
        out = OUT_DIR / f"{vdir.name}.mp3"
        assemble_mp3([samples], audio.sample_rate, out, silence_ms=0, bitrate="128k")
        dur = len(samples) / audio.sample_rate
        print(f"  ✓ {vdir.name:34s} sr={audio.sample_rate} dur={dur:4.1f}s -> {out}")


if __name__ == "__main__":
    main()
