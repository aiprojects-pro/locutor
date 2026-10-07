"""Extracción de texto de documentos .docx y .pdf con validación de tipo.

La validación se hace por *magic bytes* (contenido real), no solo por la
extensión del nombre, para evitar archivos disfrazados.
"""

from __future__ import annotations

import io

from docx import Document
from docx.oxml.ns import qn
from pypdf import PdfReader

_P, _TBL, _TR, _TC = qn("w:p"), qn("w:tbl"), qn("w:tr"), qn("w:tc")
_T, _TAB, _BR, _CR = qn("w:t"), qn("w:tab"), qn("w:br"), qn("w:cr")
_SDT, _SDT_CONTENT, _CUSTOM_XML = qn("w:sdt"), qn("w:sdtContent"), qn("w:customXml")
_TXBX = qn("w:txbxContent")
_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
_DEL = qn("w:del")
_CELL_SEP_PUNCT = ".:;!?…"


def _has_ancestor(el, tags, stop) -> bool:
    """¿Tiene ``el`` algún ancestro con etiqueta en ``tags`` antes de llegar a ``stop``?"""
    for a in el.iterancestors():
        if a is stop:
            return False
        if a.tag in tags:
            return True
    return False


def _owned(owner, tag):
    """Descendientes ``tag`` de ``owner`` sin otro ``owner.tag`` intermedio
    (p. ej. filas de esta tabla, no de una anidada; admite envoltorios sdt)."""
    return [d for d in owner.iter(tag)
            if not _has_ancestor(d, (owner.tag,), stop=owner)]


def _paragraph_text(p) -> str:
    out: list[str] = []
    for el in p.iter(_T, _TAB, _BR, _CR):
        # Texto que no se lee: copia VML duplicada de los cuadros de texto,
        # el propio cuadro de texto (se recorre aparte) y lo borrado con control de cambios.
        if _has_ancestor(el, (_MC_FALLBACK, _TXBX, _DEL), stop=p):
            continue
        out.append(el.text or "" if el.tag == _T else " ")
    return "".join(out).strip()


def _text_boxes(p):
    return [t for t in p.iter(_TXBX)
            if not _has_ancestor(t, (_MC_FALLBACK, _TXBX), stop=p)]


def _join_cells(cells: list[str]) -> str:
    """Une las celdas de una fila con '. ' (pausa al locutar)."""
    out, prev = "", ""
    for c in cells:
        if not out:
            out = c
        elif out[-1] in _CELL_SEP_PUNCT or not any(ch.isalnum() for ch in prev):
            # Ya hay puntuación, o la celda anterior es solo un icono (■, ★).
            out = f"{out} {c}"
        else:
            out = f"{out}. {c}"
        prev = c
    return out


def _walk(container, lines: list[str]) -> None:
    """Recorre bloques en orden de lectura: párrafos, tablas (y anidadas),
    controles de contenido, customXml y cuadros de texto."""
    for child in container:
        tag = child.tag
        if tag == _P:
            text = _paragraph_text(child)
            if text:
                lines.append(text)
            for box in _text_boxes(child):
                _walk(box, lines)
        elif tag == _TBL:
            # Filas de esta tabla (las de tablas anidadas se tratan en su celda).
            for tr in _owned(child, _TR):
                cells: list[str] = []
                for tc in [c for c in tr.iter(_TC)
                           if not _has_ancestor(c, (_TC,), stop=tr)]:
                    cell_lines: list[str] = []
                    _walk(tc, cell_lines)
                    if cell_lines:
                        cells.append("\n".join(cell_lines))
                if cells:
                    lines.append(_join_cells(cells))
        elif tag == _SDT:
            content = child.find(_SDT_CONTENT)
            if content is not None:
                _walk(content, lines)
        elif tag == _CUSTOM_XML:
            _walk(child, lines)


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
    lines: list[str] = []
    _walk(document.element.body, lines)
    return "\n".join(lines)


def extract_text(filename: str, data: bytes) -> str:
    """Extrae el texto de un documento .pdf o .docx validando su contenido."""
    kind = detect_kind(filename, data)
    if kind == "pdf":
        return extract_pdf(data)
    return extract_docx(data)
