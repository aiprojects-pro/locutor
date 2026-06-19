"""División de texto largo en fragmentos por límites de frase.

Respeta ¿ ¡ (aperturas) y no parte tras abreviaturas conocidas. Después agrupa
frases en fragmentos de tamaño acotado (``max_chars``) para limitar el trabajo
de cada generación nativa.
"""

from __future__ import annotations

import re

# Abreviaturas tras las que un punto NO termina la frase.
_ABBREV = {
    "sr", "sra", "srta", "dr", "dra", "d", "dña", "prof", "av", "avda",
    "núm", "pág", "tel", "ud", "uds", "ee", "uu", "etc", "p", "ej", "vs",
    "art", "fig", "núms", "máx", "mín", "núm",
}

# Punto/exclamación/interrogación de cierre seguido de espacio.
_SENT_BOUNDARY = re.compile(r"(?<=[.!?…])\s+")


def _ends_with_abbrev(fragment: str) -> bool:
    tokens = fragment.split()
    if not tokens:
        return False
    last = tokens[-1].rstrip(".!?…").lower()
    return last in _ABBREV


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    raw = _SENT_BOUNDARY.split(text)
    out: list[str] = []
    for part in raw:
        part = part.strip()
        if not part:
            continue
        if out and _ends_with_abbrev(out[-1]):
            out[-1] = f"{out[-1]} {part}"
        else:
            out.append(part)
    return out


def _hard_split(sentence: str, max_chars: int) -> list[str]:
    """Parte una frase demasiado larga por comas y, si hace falta, por espacios."""
    pieces: list[str] = []
    for piece in re.split(r"(?<=,)\s+", sentence):
        if len(piece) <= max_chars:
            pieces.append(piece)
            continue
        words = piece.split(" ")
        cur = ""
        for w in words:
            if cur and len(cur) + 1 + len(w) > max_chars:
                pieces.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}".strip()
        if cur:
            pieces.append(cur)
    return [p.strip() for p in pieces if p.strip()]


def pack_chunks(sentences: list[str], max_chars: int) -> list[str]:
    chunks: list[str] = []
    cur = ""
    for s in sentences:
        if len(s) > max_chars:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.extend(_hard_split(s, max_chars))
            continue
        if cur and len(cur) + 1 + len(s) > max_chars:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip() if cur else s
    if cur:
        chunks.append(cur)
    return chunks


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Texto -> lista de fragmentos en orden, cada uno <= max_chars."""
    return pack_chunks(split_sentences(text), max_chars)
