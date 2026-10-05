from __future__ import annotations

import io
from dataclasses import FrozenInstanceError
from typing import Any

import pytest  # type: ignore[import-not-found]
from pypdf import PdfReader, PdfWriter  # type: ignore[import-not-found]
from reportlab.pdfgen import canvas  # type: ignore[import-not-found]

from shared.document_identity import derive_document_id  # type: ignore[import-not-found]

import loader.pdf_document as pdf_document  # type: ignore[import-not-found]
from loader.pdf_document import (  # type: ignore[import-not-found]
    PDFRejected,
    parse_document,
    passage_text,
)


def _pdf_bytes(*pages: str) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output)
    for page_text in pages:
        text = document.beginText(50, 790)
        for source_line in page_text.splitlines() or [""]:
            line = source_line
            while line:
                text.textLine(line[:95])
                line = line[95:]
            if not source_line:
                text.textLine("")
        document.drawText(text)
        document.showPage()
    document.save()
    return output.getvalue()


def _encrypted_pdf_bytes() -> bytes:
    reader = PdfReader(io.BytesIO(_pdf_bytes("Contenido secreto suficiente para probar cifrado.")))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt("clave")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _assert_rejected(call, expected_reason: str) -> None:
    with pytest.raises(PDFRejected) as captured:
        call()
    assert captured.value.reason == expected_reason
    assert str(captured.value) == expected_reason


def test_parse_valid_document_preserves_page_provenance_overlap_and_identity() -> None:
    long_page = " ".join(f"termino{i:04d}" for i in range(260))
    pdf_bytes = _pdf_bytes(long_page, "Segunda página con texto útil y procedencia propia.")

    parsed = parse_document(pdf_bytes, " ../Informe\\final\n2026 ", "application/pdf", 1)

    # La identidad depende del contenido y de la organización (ver shared/document_identity.py).
    assert parsed.document_id == derive_document_id(1, parsed.sha256)
    assert parsed.version == 1
    assert parsed.object_key == (
        f"uploads/org-1/{parsed.document_id}/v1/{parsed.sha256}.pdf"
    )
    assert parsed.byte_count == len(pdf_bytes)
    assert parsed.page_count == 2
    assert parsed.title == ".. Informe final 2026"
    assert "/" not in parsed.title and "\\" not in parsed.title
    assert [chunk.chunk_index for chunk in parsed.chunks] == list(range(len(parsed.chunks)))
    assert {chunk.page for chunk in parsed.chunks} == {1, 2}
    assert all(
        chunk.section.startswith(f"Página {chunk.page}, fragmento ")
        for chunk in parsed.chunks
    )
    assert all(len(chunk.content) <= 1200 for chunk in parsed.chunks)
    assert all(chunk.document_id == parsed.document_id for chunk in parsed.chunks)
    assert all(chunk.object_key == parsed.object_key for chunk in parsed.chunks)

    page_one_chunks = [chunk for chunk in parsed.chunks if chunk.page == 1]
    assert len(page_one_chunks) >= 2
    first_words = page_one_chunks[0].content.split()
    second_words = page_one_chunks[1].content.split()
    overlap_words = 0
    for candidate in range(1, min(len(first_words), len(second_words)) + 1):
        if first_words[-candidate:] == second_words[:candidate]:
            overlap_words = candidate
    overlap_text = " ".join(second_words[:overlap_words])
    assert 150 <= len(overlap_text) < 175
    assert not (set(page_one_chunks[-1].content.split()) & set(parsed.chunks[-1].content.split()))
    assert passage_text(parsed.chunks[0]).startswith(
        f"{parsed.chunks[0].section}. "
    )
    assert not passage_text(parsed.chunks[0]).startswith("passage:")

    with pytest.raises(FrozenInstanceError):
        parsed.version = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        parsed.chunks[0].page = 9  # type: ignore[misc]


def test_identical_bytes_keep_id_and_different_bytes_change_it() -> None:
    original = _pdf_bytes("Texto original suficientemente significativo para indexar.")
    modified = _pdf_bytes("Texto modificado suficientemente significativo para indexar.")

    first = parse_document(original, "Título uno", "application/pdf", 1)
    repeated = parse_document(original, "Otro título", "application/pdf; charset=binary", 1)
    changed = parse_document(modified, "Título uno", "APPLICATION/PDF", 1)

    assert first.document_id == repeated.document_id
    assert first.sha256 == repeated.sha256
    assert first.object_key == repeated.object_key
    assert first.chunks == repeated.chunks
    assert first.title == "Título uno"
    assert repeated.title == "Otro título"
    assert first.title != repeated.title
    assert changed.document_id != first.document_id


def test_title_is_metadata_only_and_bounded() -> None:
    parsed = parse_document(
        _pdf_bytes("Texto suficiente para validar un título muy extenso."),
        "/ruta\\privada/" + "x" * 300,
        "application/pdf",
        1,
    )

    assert len(parsed.title) == pdf_document.MAX_TITLE_CHARS
    assert "/" not in parsed.title and "\\" not in parsed.title
    assert parsed.title not in parsed.object_key


@pytest.mark.parametrize(
    ("payload", "content_type", "reason"),
    [
        (b"%PDF-1.4", "text/plain", "El tipo de archivo declarado debe ser application/pdf."),
        (b"no es un PDF", "application/pdf", "El archivo no tiene la firma de un PDF válido."),
        (b"", "application/pdf", "El PDF debe contener entre 1 byte y 50 MiB."),
    ],
)
def test_rejects_wrong_mime_magic_and_empty_payload(
    payload: bytes, content_type: str, reason: str
) -> None:
    _assert_rejected(lambda: parse_document(payload, "Informe", content_type, 1), reason)


def test_rejects_more_than_50_mib_before_starting_parser(monkeypatch) -> None:
    def parser_must_not_run(*args, **kwargs):
        raise AssertionError("PdfReader no debe ejecutarse")

    monkeypatch.setattr(pdf_document, "PdfReader", parser_must_not_run)
    oversized = b"%PDF" + b"x" * (pdf_document.MAX_PDF_BYTES - 3)

    _assert_rejected(
        lambda: parse_document(oversized, "Informe", "application/pdf", 1),
        "El PDF debe contener entre 1 byte y 50 MiB.",
    )


def test_rejects_blank_or_scanned_document_without_ocr() -> None:
    blank = _pdf_bytes("")

    _assert_rejected(
        lambda: parse_document(blank, "Escaneo", "application/pdf", 1),
        "El PDF no contiene texto extraíble significativo; no se aplica OCR.",
    )


def test_rejects_encrypted_document() -> None:
    _assert_rejected(
        lambda: parse_document(_encrypted_pdf_bytes(), "Privado", "application/pdf", 1),
        "No se aceptan PDFs cifrados.",
    )


def test_accepts_more_than_20_pages_without_a_page_cap() -> None:
    pdf_bytes = _pdf_bytes(*(f"Texto significativo de la página {page}." for page in range(25)))

    parsed = parse_document(pdf_bytes, "Extenso", "application/pdf", 1)

    assert parsed.page_count == 25
    assert {chunk.page for chunk in parsed.chunks} == set(range(1, 26))


class _FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakeReader:
    is_encrypted = False

    def __init__(self, pages: Any) -> None:
        self.pages = pages


class _BrokenLazyPages:
    def __len__(self) -> int:
        return 1

    def __getitem__(self, index: int) -> Any:
        raise RuntimeError("SENTINEL sensitive parser detail")


def test_wraps_lazy_page_access_error_with_safe_reason(monkeypatch) -> None:
    monkeypatch.setattr(
        pdf_document,
        "PdfReader",
        lambda *args, **kwargs: _FakeReader(_BrokenLazyPages()),
    )

    with pytest.raises(PDFRejected) as captured:
        parse_document(b"%PDF mock", "Informe", "application/pdf", 1)

    assert str(captured.value) == "No se pudo extraer el texto del PDF."
    assert "SENTINEL" not in str(captured.value)


def test_page_fragments_terminate_for_long_unbroken_token() -> None:
    token = "".join(character * 1_200 for character in "abcd") + "e" * 203

    fragments = pdf_document._page_fragments(token)

    assert fragments == [
        token[offset : offset + pdf_document.MAX_CHUNK_CHARS]
        for offset in range(0, len(token), pdf_document.MAX_CHUNK_CHARS)
    ]
    assert all(len(fragment) <= 1_200 for fragment in fragments)
    assert "".join(fragments) == token

    overlap_lengths = [
        max(
            (
                size
                for size in range(1, min(len(left), len(right)) + 1)
                if left[-size:] == right[:size]
            ),
            default=0,
        )
        for left, right in zip(fragments, fragments[1:], strict=False)
    ]
    assert all(overlap <= 120 for overlap in overlap_lengths)


def test_accepts_page_and_total_text_beyond_former_limits(monkeypatch) -> None:
    long_page = _FakeReader([_FakePage("a" * 20_001)])
    monkeypatch.setattr(pdf_document, "PdfReader", lambda *args, **kwargs: long_page)
    parsed = parse_document(b"%PDF mock", "Informe", "application/pdf", 1)
    assert parsed.extracted_char_count == 20_001

    total_long = _FakeReader([_FakePage("palabra " * 2500) for _ in range(11)])
    monkeypatch.setattr(pdf_document, "PdfReader", lambda *args, **kwargs: total_long)
    parsed = parse_document(b"%PDF mock", "Informe", "application/pdf", 1)
    assert parsed.extracted_char_count > 200_000


def test_accepts_more_than_120_chunks(monkeypatch) -> None:
    many_chunks = _FakeReader(
        [_FakePage(" ".join(f"palabra{i}" for i in range(1600))) for _ in range(10)]
    )
    monkeypatch.setattr(pdf_document, "PdfReader", lambda *args, **kwargs: many_chunks)

    parsed = parse_document(b"%PDF mock", "Informe", "application/pdf", 1)

    assert len(parsed.chunks) > 120


def test_wraps_parser_and_extraction_errors_with_safe_reasons(monkeypatch) -> None:
    def broken_reader(*args, **kwargs):
        raise RuntimeError("detalle interno sensible")

    monkeypatch.setattr(pdf_document, "PdfReader", broken_reader)
    _assert_rejected(
        lambda: parse_document(b"%PDF mock", "Informe", "application/pdf", 1),
        "No se pudo interpretar el PDF.",
    )

    class BrokenPage:
        def extract_text(self) -> str:
            raise RuntimeError("detalle interno sensible")

    monkeypatch.setattr(
        pdf_document,
        "PdfReader",
        lambda *args, **kwargs: _FakeReader([BrokenPage()]),
    )
    _assert_rejected(
        lambda: parse_document(b"%PDF mock", "Informe", "application/pdf", 1),
        "No se pudo extraer el texto del PDF.",
    )
