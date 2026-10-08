"""Ensamblado de audio y transcodificación a MP3.

- Une los fragmentos en orden, con un breve silencio entre ellos para evitar
  "clicks", preservando un único sample rate.
- Escribe un WAV (PCM_16) temporal y lo convierte a MP3 con ffmpeg.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import soundfile as sf


def _ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg no está instalado (necesario para MP3).")
    return path


def merge_with_silence(
    chunks: list[np.ndarray], sample_rate: int, silence_ms: int
) -> np.ndarray:
    """Concatena fragmentos float32 intercalando silencio."""
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    silence = np.zeros(int(sample_rate * silence_ms / 1000), dtype=np.float32)
    out: list[np.ndarray] = []
    for i, c in enumerate(chunks):
        if i > 0:
            out.append(silence)
        out.append(np.asarray(c, dtype=np.float32))
    return np.concatenate(out)


def write_wav(samples: np.ndarray, sample_rate: int, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), samples, samplerate=sample_rate, subtype="PCM_16")
    return path


def wav_to_mp3(wav_path: Path, mp3_path: Path, bitrate: str = "128k") -> Path:
    """Convierte WAV -> MP3 (mono) con ffmpeg."""
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _ffmpeg_bin(), "-y", "-loglevel", "error",
        "-i", str(wav_path),
        "-codec:a", "libmp3lame", "-b:a", bitrate, "-ac", "1",
        str(mp3_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return mp3_path


def write_wav_chunks(
    chunks: Iterable[np.ndarray], sample_rate: int, path: Path, silence_ms: int
) -> Path:
    """Escribe los fragmentos en un WAV (PCM_16) a medida que llegan.

    Equivale a write_wav(merge_with_silence(...)) pero sin tener todo el audio
    en memoria: acepta un generador y solo retiene un fragmento cada vez.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    silence = np.zeros(int(sample_rate * silence_ms / 1000), dtype=np.float32)
    with sf.SoundFile(
        str(path), mode="w", samplerate=sample_rate, channels=1, subtype="PCM_16"
    ) as f:
        for i, c in enumerate(chunks):
            if i > 0:
                f.write(silence)
            f.write(np.asarray(c, dtype=np.float32))
    return path


def assemble_mp3(
    chunks: Iterable[np.ndarray],
    sample_rate: int,
    out_mp3: Path,
    silence_ms: int,
    bitrate: str,
) -> Path:
    """Pipeline completo: fragmentos -> WAV temporal -> MP3.

    `chunks` puede ser un generador: se consume en streaming.
    """
    wav_tmp = out_mp3.with_suffix(".wav")
    try:
        write_wav_chunks(chunks, sample_rate, wav_tmp, silence_ms)
        wav_to_mp3(wav_tmp, out_mp3, bitrate)
    finally:
        wav_tmp.unlink(missing_ok=True)
    return out_mp3
