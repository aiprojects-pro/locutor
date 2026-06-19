import io

import pytest
from docx import Document

from app.docs.extract import UnsupportedFileError, detect_kind, extract_text


def _make_docx(text: str) -> bytes:
    doc = Document()
    for line in text.split("\n"):
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_detect_pdf_by_magic():
    assert detect_kind("algo.pdf", b"%PDF-1.7\n...") == "pdf"


def test_detect_docx_by_magic_and_ext():
    data = _make_docx("hola")
    assert detect_kind("doc.docx", data) == "docx"


def test_reject_unknown():
    with pytest.raises(UnsupportedFileError):
        detect_kind("evil.exe", b"MZ\x90\x00")


def test_extract_docx_text():
    data = _make_docx("Primera línea\nSegunda línea")
    out = extract_text("doc.docx", data)
    assert "Primera línea" in out
    assert "Segunda línea" in out
