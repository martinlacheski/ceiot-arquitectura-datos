"""API FastAPI mínima para los tres flujos de IA de la práctica."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, unquote

import httpx  # type: ignore[import-not-found]
from fastapi import (  # type: ignore[import-not-found]
    FastAPI,
    Header,
    HTTPException,
    Request,
)
from fastapi.responses import FileResponse  # type: ignore[import-not-found]
from pydantic import (  # type: ignore[import-not-found]
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from api import workflows  # type: ignore[import-not-found]
from api.openrouter_client import (  # type: ignore[import-not-found]
    MissingOpenRouterKey,
    OpenRouterError,
)
from loader.pdf_document import (  # type: ignore[import-not-found]
    MAX_PDF_BYTES,
    MAX_TITLE_CHARS,
)
from shared import document_catalog  # type: ignore[import-not-found]
from shared.rag_connection import validate_document_id  # type: ignore[import-not-found]
from shared.sql_guard import SQLRejected  # type: ignore[import-not-found]

app = FastAPI(title="Laboratorio IoT Clase 06", version="1.0.0")
INDEX_HTML = Path(__file__).with_name("static") / "index.html"
PDF_CONTENT_TYPE = "application/pdf"
UPLOADER_URL = "http://uploader:8007/internal/documents"
UPLOADER_TIMEOUT_SECONDS = 240.0
MAX_ENCODED_TITLE_CHARS = 1200
_BAD_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    mode: Literal["rag", "text-to-sql", "integrated"]
    top_k: int = Field(default=4, ge=1, le=4)
    document_id: str | None = None

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("La pregunta debe tener al menos 3 caracteres")
        return cleaned

    @field_validator("document_id")
    @classmethod
    def validate_selected_document(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_document_id(value)


class QueryResponse(BaseModel):
    answer: str
    sql: str | None
    rows: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    trace: list[str]


class UploadSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    document_id: str = Field(pattern=r"^upload-[0-9a-f]{24}$")
    version: Literal[1]
    title: str = Field(min_length=1, max_length=200)
    object_key: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_count: int = Field(ge=1, le=MAX_PDF_BYTES)
    page_count: int = Field(ge=1, le=20)
    extracted_char_count: int = Field(ge=1, le=200_000)
    chunk_count: int = Field(ge=1, le=120)
    embedding_model: Literal["BAAI/bge-m3"]
    dimension: Literal[1024]
    index_status: Literal["indexed"]
    embedding_preview: list[float] = Field(min_length=6, max_length=6)
    trace: list[str] = Field(min_length=5, max_length=5)

    @field_validator("embedding_preview")
    @classmethod
    def validate_finite_preview(cls, value: list[float]) -> list[float]:
        if not all(math.isfinite(component) for component in value):
            raise ValueError("embedding preview must contain only finite values")
        return value

    @field_validator("trace")
    @classmethod
    def validate_trace(cls, value: list[str]) -> list[str]:
        if value != [
            "pdf_validated",
            "chunks_embedded",
            "s3_stored",
            "s3_verified",
            "postgres_indexed",
        ]:
            raise ValueError("unexpected upload trace")
        return value

    @model_validator(mode="after")
    def validate_storage_identity(self) -> UploadSummary:
        expected_id = f"upload-{self.sha256[:24]}"
        expected_key = f"uploads/{expected_id}/v1/{self.sha256}.pdf"
        if self.document_id != expected_id or self.object_key != expected_key:
            raise ValueError("incoherent upload storage identity")
        return self


@app.get("/", response_class=FileResponse)
def root() -> FileResponse:
    return FileResponse(INDEX_HTML, media_type="text/html; charset=utf-8")


@app.get("/health")
def health() -> dict[str, str]:
    # Deliberadamente no carga E5, no consulta la base y no llama a OpenRouter.
    return {"status": "ok"}


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


def _encoded_title(raw_title: str | None) -> str | None:
    if raw_title is None:
        return None
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
    return quote(decoded, safe="", encoding="utf-8", errors="strict")


def _upstream_detail(response: httpx.Response, status_code: int) -> str:
    defaults = {
        422: "El PDF no pudo ser procesado.",
        429: "Ya hay una carga en proceso; intentá nuevamente más tarde.",
        503: "La carga no está disponible temporalmente.",
    }
    try:
        payload = response.json()
    except ValueError:
        return defaults[status_code]
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if not isinstance(detail, str):
        return defaults[status_code]
    bounded = " ".join(detail.split())[:300]
    return bounded or defaults[status_code]


@app.get("/api/documents")
def list_documents() -> list[dict[str, Any]]:
    try:
        return document_catalog.list_documents()
    except document_catalog.CatalogUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/documents/{document_id}")
def document_details(document_id: str) -> dict[str, Any]:
    try:
        selected_id = validate_document_id(document_id)
        details = document_catalog.document_details(selected_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except document_catalog.CatalogUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if details is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    return details


@app.post("/api/documents")
async def upload_document(
    request: Request,
    document_title: str | None = Header(
        default=None,
        alias="X-Document-Title",
        max_length=MAX_ENCODED_TITLE_CHARS,
    ),
) -> dict[str, Any]:
    if _declared_mime(request) != PDF_CONTENT_TYPE:
        raise HTTPException(
            status_code=415,
            detail="El tipo de contenido debe ser application/pdf.",
        )
    _reject_known_oversize(request)
    encoded_title = _encoded_title(document_title)
    pdf_bytes = await _bounded_body(request)
    headers = {"Content-Type": PDF_CONTENT_TYPE}
    if encoded_title is not None:
        headers["X-Document-Title"] = encoded_title

    try:
        async with httpx.AsyncClient(timeout=UPLOADER_TIMEOUT_SECONDS) as client:
            response = await client.post(
                UPLOADER_URL,
                content=pdf_bytes,
                headers=headers,
            )
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=503,
            detail="La carga no está disponible temporalmente.",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="El servicio de carga devolvió una respuesta inválida.",
        ) from error

    if response.status_code in {422, 429, 503}:
        raise HTTPException(
            status_code=response.status_code,
            detail=_upstream_detail(response, response.status_code),
        )
    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="El servicio de carga devolvió una respuesta inválida.",
        )
    try:
        summary = UploadSummary.model_validate(response.json())
        if summary.byte_count != len(pdf_bytes):
            raise ValueError("upstream byte count does not match request body")
    except (ValueError, ValidationError, TypeError) as error:
        raise HTTPException(
            status_code=502,
            detail="El servicio de carga devolvió una respuesta inválida.",
        ) from error
    return summary.model_dump()


@app.post("/api/query", response_model=QueryResponse)
def query(request: QueryRequest) -> dict[str, Any]:
    if request.mode == "text-to-sql" and request.document_id is not None:
        raise HTTPException(
            status_code=422,
            detail="El modo text-to-sql no admite filtro por documento.",
        )
    try:
        workflow = workflows.WORKFLOWS[request.mode]
        if request.document_id is None:
            return workflow(request.question, request.top_k)
        return workflow(
            request.question,
            request.top_k,
            document_id=request.document_id,
        )
    except MissingOpenRouterKey as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except SQLRejected as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except workflows.ServiceUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except OpenRouterError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
