"""Internal, bounded HTTP entry point for PDF document ingestion."""

from __future__ import annotations

import re
import threading
from typing import Any
from urllib.parse import unquote

from fastapi import (  # type: ignore[import-not-found]
    FastAPI,
    Header,
    HTTPException,
    Request,
)
from starlette.concurrency import run_in_threadpool  # type: ignore[import-not-found]

from loader import pdf_storage
from loader.pdf_document import MAX_PDF_BYTES, MAX_TITLE_CHARS, PDFRejected
from loader.pdf_storage import UploadUnavailable

PDF_CONTENT_TYPE = "application/pdf"
DEFAULT_TITLE = "Documento PDF"
MAX_ENCODED_TITLE_CHARS = 1200
_BAD_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_INGESTION_GATE = threading.Lock()

app = FastAPI(title="Internal PDF uploader", docs_url=None, redoc_url=None)


def _declared_mime(request: Request) -> str:
    return request.headers.get("content-type", "").partition(";")[0].strip().lower()


def _reject_known_oversize(request: Request) -> None:
    raw_length = request.headers.get("content-length")
    if raw_length is None:
        return
    try:
        content_length = int(raw_length)
    except ValueError:
        return
    if content_length > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="El PDF supera el límite de 10 MiB.")


async def _bounded_body(request: Request) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_PDF_BYTES:
            raise HTTPException(
                status_code=413,
                detail="El PDF supera el límite de 10 MiB.",
            )
        body.extend(chunk)
    return bytes(body)


def _decoded_title(raw_title: str | None) -> str:
    if raw_title is None:
        return DEFAULT_TITLE
    if _BAD_PERCENT_ESCAPE.search(raw_title):
        raise HTTPException(status_code=422, detail="El título del documento no es válido.")
    try:
        decoded = unquote(raw_title, encoding="utf-8", errors="strict")
    except (UnicodeDecodeError, ValueError) as error:
        raise HTTPException(
            status_code=422,
            detail="El título del documento no es válido.",
        ) from error
    if len(decoded) > MAX_TITLE_CHARS:
        raise HTTPException(
            status_code=422,
            detail="El título del documento supera los 200 caracteres.",
        )
    return decoded


@app.get("/health")
def health() -> dict[str, str]:
    """Report process availability without touching models or infrastructure."""

    return {"status": "ok"}


@app.post("/internal/documents")
async def upload_document(
    request: Request,
    document_title: str | None = Header(
        default=None,
        alias="X-Document-Title",
        max_length=MAX_ENCODED_TITLE_CHARS,
    ),
) -> dict[str, Any]:
    """Read one raw PDF into a bounded buffer and ingest it off the event loop."""

    if _declared_mime(request) != PDF_CONTENT_TYPE:
        raise HTTPException(
            status_code=415,
            detail="El tipo de contenido debe ser application/pdf.",
        )
    _reject_known_oversize(request)
    title = _decoded_title(document_title)

    if not _INGESTION_GATE.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="Ya hay una carga en proceso; intentá nuevamente más tarde.",
        )

    try:
        pdf_bytes = await _bounded_body(request)
        return await run_in_threadpool(
            pdf_storage.ingest_document,
            pdf_bytes,
            title,
            PDF_CONTENT_TYPE,
        )
    except PDFRejected as error:
        raise HTTPException(status_code=422, detail=error.reason) from error
    except UploadUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="La carga no está disponible temporalmente.",
        ) from error
    finally:
        _INGESTION_GATE.release()
