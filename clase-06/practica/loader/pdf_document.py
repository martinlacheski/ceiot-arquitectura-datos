"""Pure, bounded parsing and chunking for user-supplied text PDFs."""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass

from pypdf import PdfReader  # type: ignore[import-not-found]

# Single remaining cap: the PDF is read fully into memory (app proxy, uploader
# and parser all agree on this value; see also the DB CHECK in
# postgres/init/05-document-upload.sql). Page count, per-page/total extracted
# characters and chunk count are unbounded: chunks scale with the document.
MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_CHUNK_CHARS = 1_200
CHUNK_OVERLAP_CHARS = 150
MAX_TITLE_CHARS = 200


class PDFRejected(ValueError):
    """Expected rejection whose reason is safe to show to a Spanish-speaking user."""

    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class PageChunk:
    document_id: str
    version: int
    page: int
    section: str
    chunk_index: int
    content: str
    object_key: str


@dataclass(frozen=True)
class ParsedDocument:
    document_id: str
    version: int
    title: str
    sha256: str
    byte_count: int
    page_count: int
    extracted_char_count: int
    object_key: str
    chunks: tuple[PageChunk, ...]


def _safe_title(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title)
    without_controls = "".join(
        " " if unicodedata.category(character).startswith("C") else character
        for character in normalized
    )
    without_path_separators = without_controls.replace("/", " ").replace("\\", " ")
    bounded = " ".join(without_path_separators.split())[:MAX_TITLE_CHARS].strip()
    return bounded or "Documento PDF"


def _normalized_text(text: str) -> str:
    return " ".join(text.split())


def _word_units(text: str) -> list[str]:
    units: list[str] = []
    for word in text.split():
        if len(word) <= MAX_CHUNK_CHARS:
            units.append(word)
            continue
        units.extend(
            word[offset : offset + MAX_CHUNK_CHARS]
            for offset in range(0, len(word), MAX_CHUNK_CHARS)
        )
    return units


def _page_fragments(text: str) -> list[str]:
    words = _word_units(text)
    fragments: list[str] = []
    start = 0

    while start < len(words):
        end = start
        fragment_length = 0
        while end < len(words):
            separator_length = 1 if end > start else 0
            proposed_length = fragment_length + separator_length + len(words[end])
            if proposed_length > MAX_CHUNK_CHARS:
                break
            fragment_length = proposed_length
            end += 1

        if end == start:
            # _word_units bounds every unit, so this is only a defensive guard.
            end += 1

        fragments.append(" ".join(words[start:end]))
        if end == len(words):
            break

        next_start = end
        overlap_length = 0
        while next_start > start + 1 and overlap_length < CHUNK_OVERLAP_CHARS:
            next_start -= 1
            overlap_length += len(words[next_start])
            if next_start < end - 1:
                overlap_length += 1
        start = next_start

    return fragments


def _meaningful(text: str) -> bool:
    alphanumeric_count = sum(character.isalnum() for character in text)
    return alphanumeric_count >= 10 and bool(re.search(r"\w", text, flags=re.UNICODE))


def _chunks_from_pages(
    page_texts: list[str], document_id: str, object_key: str
) -> tuple[PageChunk, ...]:
    chunks: list[PageChunk] = []
    for page_number, page_text in enumerate(page_texts, start=1):
        normalized = _normalized_text(page_text)
        if not normalized:
            continue
        for fragment_number, content in enumerate(_page_fragments(normalized), start=1):
            chunks.append(
                PageChunk(
                    document_id=document_id,
                    version=1,
                    page=page_number,
                    section=f"Página {page_number}, fragmento {fragment_number}",
                    chunk_index=len(chunks),
                    content=content,
                    object_key=object_key,
                )
            )
    return tuple(chunks)


def parse_document(pdf_bytes: bytes, title: str, content_type: str) -> ParsedDocument:
    """Validate, extract and chunk one PDF without storage or model side effects."""

    declared_mime = content_type.partition(";")[0].strip().lower()
    if declared_mime != "application/pdf":
        raise PDFRejected("El tipo de archivo declarado debe ser application/pdf.")

    byte_count = len(pdf_bytes)
    if not 1 <= byte_count <= MAX_PDF_BYTES:
        raise PDFRejected("El PDF debe contener entre 1 byte y 50 MiB.")
    if not pdf_bytes.startswith(b"%PDF"):
        raise PDFRejected("El archivo no tiene la firma de un PDF válido.")

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=True)
        encrypted = reader.is_encrypted
    except Exception as error:
        raise PDFRejected("No se pudo interpretar el PDF.") from error

    if encrypted:
        raise PDFRejected("No se aceptan PDFs cifrados.")
    try:
        page_count = len(reader.pages)
    except Exception as error:
        raise PDFRejected("No se pudo interpretar el PDF.") from error
    if page_count < 1:
        raise PDFRejected("El PDF debe tener al menos 1 página.")

    page_texts: list[str] = []
    extracted_char_count = 0
    for page_index in range(page_count):
        try:
            page_text = reader.pages[page_index].extract_text() or ""
        except Exception as error:
            raise PDFRejected("No se pudo extraer el texto del PDF.") from error
        extracted_char_count += len(page_text)
        page_texts.append(page_text)

    combined_text = " ".join(_normalized_text(text) for text in page_texts)
    if not _meaningful(combined_text):
        raise PDFRejected(
            "El PDF no contiene texto extraíble significativo; no se aplica OCR."
        )

    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    document_id = f"upload-{sha256[:24]}"
    object_key = f"uploads/{document_id}/v1/{sha256}.pdf"
    chunks = _chunks_from_pages(page_texts, document_id, object_key)
    if not chunks:
        raise PDFRejected(
            "El PDF no contiene texto extraíble significativo; no se aplica OCR."
        )

    return ParsedDocument(
        document_id=document_id,
        version=1,
        title=_safe_title(title),
        sha256=sha256,
        byte_count=byte_count,
        page_count=page_count,
        extracted_char_count=extracted_char_count,
        object_key=object_key,
        chunks=chunks,
    )


def passage_text(chunk: PageChunk) -> str:
    """Return the passage input without loading the embedding model.

    bge-m3 does not use E5-style query/passage prefixes.
    """

    return f"{chunk.section}. {chunk.content}"
