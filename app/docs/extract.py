"""Extracción de texto de documentos .docx y .pdf con validación de tipo.

La validación se hace por *magic bytes* (contenido real), no solo por la
extensión del nombre, para evitar archivos disfrazados.
"""

from __future__ import annotations

import io

from docx import Document
from pypdf import PdfReader


class UnsupportedFileError(ValueError):
    """El archivo no es un .docx ni un .pdf válido."""


def _looks_like_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def _looks_like_zip(data: bytes) -> bool:
    # Los .docx son contenedores ZIP (OOXML): empiezan por 'PK\x03\x04'.
    return data[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def detect_kind(filename: str, data: bytes) -> str:
    """Devuelve 'pdf' o 'docx' según el contenido. Lanza si no coincide."""
    name = (filename or "").lower()
    if _looks_like_pdf(data):
        return "pdf"
    if _looks_like_zip(data) and name.endswith(".docx"):
        return "docx"
    raise UnsupportedFileError(
        "Formato no soportado. Solo se aceptan archivos .pdf o .docx válidos."
    )


def extract_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)
    return "\n".join(parts)


def extract_docx(data: bytes) -> str:
    document = Document(io.BytesIO(data))
    parts: list[str] = [p.text for p in document.paragraphs if p.text.strip()]
    # Texto contenido en tablas.
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" ".join(cells))
    return "\n".join(parts)


def extract_text(filename: str, data: bytes) -> str:
    """Extrae el texto de un documento .pdf o .docx validando su contenido."""
    kind = detect_kind(filename, data)
    if kind == "pdf":
        return extract_pdf(data)
    return extract_docx(data)
