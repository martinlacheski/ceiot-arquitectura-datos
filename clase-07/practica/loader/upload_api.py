"""Internal, bounded HTTP entry point for PDF document ingestion."""

from __future__ import annotations

import asyncio
import json
import queue
import re
import threading
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import unquote

from fastapi import (  # type: ignore[import-not-found]
    FastAPI,
    Header,
    HTTPException,
    Request,
)
from fastapi.responses import StreamingResponse  # type: ignore[import-not-found]
from starlette.concurrency import run_in_threadpool  # type: ignore[import-not-found]

from loader import pdf_storage
from loader.pdf_document import (
    MAX_PDF_BYTES,
    MAX_PDF_MIB,
    MAX_TITLE_CHARS,
    ParsedDocument,
    PDFRejected,
    parse_document,
)
from loader.pdf_storage import UploadUnavailable

PDF_CONTENT_TYPE = "application/pdf"
NDJSON_CONTENT_TYPE = "application/x-ndjson"
DEFAULT_TITLE = "Documento PDF"
MAX_ENCODED_TITLE_CHARS = 1200
_BAD_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
# Sólo dígitos ASCII, sin ceros a la izquierda ni signo: un entero positivo.
_ORGANIZATION_ID = re.compile(r"[1-9][0-9]{0,17}")
_INGESTION_GATE = threading.Lock()
_GENERIC_UNAVAILABLE = "La carga no está disponible temporalmente."

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
        raise HTTPException(
            status_code=413, detail=f"El PDF supera el límite de {MAX_PDF_MIB} MiB."
        )


async def _bounded_body(request: Request) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_PDF_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"El PDF supera el límite de {MAX_PDF_MIB} MiB.",
            )
        body.extend(chunk)
    return bytes(body)


def _organization_from_header(raw_value: str | None) -> int:
    """Organización dueña del documento, enviada por la API (salto interno).

    Este servicio no es público: sólo lo llama ``api/web_app.py``, que ya
    tradujo el usuario simulado a su organización. Igual se valida el formato
    acá (entero positivo). Que la organización exista lo garantiza la base: la
    clave foránea a ``organizations`` y la política RLS rechazan el INSERT.
    """

    if raw_value is None or _ORGANIZATION_ID.fullmatch(raw_value) is None:
        raise HTTPException(
            status_code=422, detail="Falta una organización válida para la carga."
        )
    return int(raw_value)


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


def _stream_error_detail(error: Exception) -> str:
    if isinstance(error, UploadUnavailable):
        return str(error)
    return _GENERIC_UNAVAILABLE


async def _event_stream(
    document: ParsedDocument, pdf_bytes: bytes, organization_id: int
) -> AsyncIterator[bytes]:
    """Run ingestion in a worker thread and relay each event as one ndjson line.

    Embedding, S3 and PostgreSQL calls are all blocking; running them in a thread and
    bridging through a queue lets each progress event reach the client as soon as it is
    produced, instead of only after the whole request completes. The ingestion gate is
    released here, once this generator is fully drained (success or failure).
    """

    events: queue.Queue[Any] = queue.Queue()
    sentinel = object()

    def runner() -> None:
        try:
            for event in pdf_storage.ingest_parsed_document_stream(
                document, pdf_bytes, organization_id
            ):
                events.put(event)
        except Exception as error:  # noqa: BLE001 - converted to a sanitized error event
            events.put({"event": "error", "detail": _stream_error_detail(error)})
        finally:
            events.put(sentinel)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    loop = asyncio.get_event_loop()
    try:
        while True:
            item = await loop.run_in_executor(None, events.get)
            if item is sentinel:
                break
            yield (json.dumps(item) + "\n").encode("utf-8")
    finally:
        _INGESTION_GATE.release()


@app.post("/internal/documents")
async def upload_document(
    request: Request,
    document_title: str | None = Header(
        default=None,
        alias="X-Document-Title",
        max_length=MAX_ENCODED_TITLE_CHARS,
    ),
    organization_header: str | None = Header(default=None, alias="X-Organization-Id"),
) -> StreamingResponse:
    """Validate and parse one raw PDF, then stream ingestion progress as ndjson.

    Validation/parsing (content type, size, PDF signature, encryption, extractable
    text) happens entirely before any response is sent, so rejections keep returning
    their normal status code and JSON error body. Only once the document is accepted
    does this switch to a 200 ``application/x-ndjson`` stream of progress events
    followed by a final ``result`` or ``error`` event.
    """

    if _declared_mime(request) != PDF_CONTENT_TYPE:
        raise HTTPException(
            status_code=415,
            detail="El tipo de contenido debe ser application/pdf.",
        )
    _reject_known_oversize(request)
    organization_id = _organization_from_header(organization_header)
    title = _decoded_title(document_title)

    if not _INGESTION_GATE.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="Ya hay una carga en proceso; intentá nuevamente más tarde.",
        )

    try:
        pdf_bytes = await _bounded_body(request)
        document = await run_in_threadpool(
            parse_document, pdf_bytes, title, PDF_CONTENT_TYPE, organization_id
        )
    except PDFRejected as error:
        _INGESTION_GATE.release()
        raise HTTPException(status_code=422, detail=error.reason) from error
    except HTTPException:
        _INGESTION_GATE.release()
        raise
    except Exception as error:
        _INGESTION_GATE.release()
        raise HTTPException(status_code=503, detail=_GENERIC_UNAVAILABLE) from error

    return StreamingResponse(
        _event_stream(document, pdf_bytes, organization_id),
        media_type=NDJSON_CONTENT_TYPE
    )
