"""API FastAPI mínima para los tres flujos de IA de la práctica."""

from __future__ import annotations

import json
import math
import re
from collections.abc import AsyncIterator
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
from fastapi.responses import HTMLResponse, StreamingResponse  # type: ignore[import-not-found]
from pydantic import (  # type: ignore[import-not-found]
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from api import workflows  # type: ignore[import-not-found]
from api.openrouter_client import (  # type: ignore[import-not-found]
    MissingOpenRouterKey,
    OpenRouterError,
)
from loader.pdf_document import (  # type: ignore[import-not-found]
    MAX_PDF_BYTES,
    MAX_PDF_MIB,
    MAX_TITLE_CHARS,
)
from shared import document_catalog  # type: ignore[import-not-found]
from shared.document_identity import (  # type: ignore[import-not-found]
    derive_document_id,
    object_key_for,
)
from shared.rag_connection import validate_document_id  # type: ignore[import-not-found]
from shared.retrieval import MAX_TOP_K  # type: ignore[import-not-found]
from shared.sql_guard import SQLRejected  # type: ignore[import-not-found]
from shared.sql_schema import SchemaUnavailable, schema_prompt  # type: ignore[import-not-found]
from shared.tenants import Tenant, list_users, resolve_user  # type: ignore[import-not-found]

app = FastAPI(title="Laboratorio IoT Clase 07", version="1.0.0")
INDEX_HTML = Path(__file__).with_name("static") / "index.html"
PDF_CONTENT_TYPE = "application/pdf"
NDJSON_CONTENT_TYPE = "application/x-ndjson"
UPLOADER_URL = "http://uploader:8007/internal/documents"
ORGANIZATION_HEADER = "X-Organization-Id"
# No total cap: uploads scale with document size. A generous per-read timeout covers
# one embedding batch on a slow CPU (measured ~4.4 s for a batch of 4 at 1.1 s/chunk;
# this leaves wide margin), while connect/write stay short since the body is already
# read into memory before this request starts.
UPLOADER_TIMEOUT = httpx.Timeout(connect=10.0, write=30.0, read=120.0, pool=10.0)
MAX_ENCODED_TITLE_CHARS = 1200
DEFAULT_TOP_K = min(4, MAX_TOP_K)
_BAD_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_UPLOAD_PROGRESS_STAGES = frozenset(
    {"pdf_validated", "chunks_embedded", "s3_stored", "s3_verified", "postgres_indexed"}
)
_GENERIC_STREAM_ERROR = "La carga no está disponible temporalmente."
_INVALID_UPSTREAM_ERROR = "El servicio de carga devolvió una respuesta inválida."


def _tenant_for(user_id: str) -> Tenant:
    """Traduce el usuario simulado a su organización; 422 si no existe."""

    try:
        return resolve_user(user_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


class QueryRequest(BaseModel):
    # extra="forbid": un organization_id o tenant_id enviado por el cliente no se
    # ignora en silencio, se rechaza. La organización sale siempre de user_id.
    model_config = ConfigDict(extra="forbid")

    user_id: str
    question: str = Field(min_length=3, max_length=500)
    mode: Literal["rag", "text-to-sql", "integrated"]
    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=MAX_TOP_K)
    document_id: str | None = None

    @field_validator("user_id")
    @classmethod
    def validate_user(cls, value: str) -> str:
        resolve_user(value)
        return value

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
    # Usuario simulado que consultó (id y etiqueta); la UI muestra "Consultando como".
    user: dict[str, str]
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
    page_count: int = Field(ge=1)
    extracted_char_count: int = Field(ge=1)
    chunk_count: int = Field(ge=1)
    embedding_model: str = Field(min_length=1, max_length=200)
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

    def check_belongs_to(self, organization_id: int) -> None:
        """La identidad se deriva de (organización, contenido): debe coincidir."""

        expected_id = derive_document_id(organization_id, self.sha256)
        expected_key = object_key_for(organization_id, expected_id, self.sha256)
        if self.document_id != expected_id or self.object_key != expected_key:
            raise ValueError("incoherent upload storage identity")


def render_index() -> str:
    """Inyecta en la UI los límites configurados: el navegador no los duplica."""

    replacements = {
        "{{MAX_PDF_MIB}}": str(MAX_PDF_MIB),
        "{{MAX_PDF_BYTES}}": str(MAX_PDF_BYTES),
        "{{MAX_TOP_K}}": str(MAX_TOP_K),
        "{{DEFAULT_TOP_K}}": str(DEFAULT_TOP_K),
    }
    html = INDEX_HTML.read_text(encoding="utf-8")
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, value)
    return html


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    return HTMLResponse(render_index())


@app.get("/health")
def health() -> dict[str, str]:
    # Deliberadamente no carga E5, no consulta la base y no llama a OpenRouter.
    return {"status": "ok"}


@app.get("/api/users")
def users() -> list[dict[str, str]]:
    return list_users()


@app.get("/api/sql-schema")
def sql_schema(user_id: str) -> dict[str, str]:
    # Muestra exactamente el esquema que Text-to-SQL envía al modelo, con los
    # valores de ejemplo que ve la organización del usuario.
    tenant = _tenant_for(user_id)
    try:
        prompt = schema_prompt(tenant.organization_id)
    except SchemaUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"source": prompt.source, "text": prompt.text}


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
        raise HTTPException(status_code=413, detail=f"El PDF supera el límite de {MAX_PDF_MIB} MiB.")


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


def _upstream_detail(payload: Any, status_code: int) -> str:
    defaults = {
        422: "El PDF no pudo ser procesado.",
        429: "Ya hay una carga en proceso; intentá nuevamente más tarde.",
        503: "La carga no está disponible temporalmente.",
    }
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if not isinstance(detail, str):
        return defaults[status_code]
    bounded = " ".join(detail.split())[:300]
    return bounded or defaults[status_code]


def _sanitized_detail(detail: Any) -> str:
    if not isinstance(detail, str):
        return _GENERIC_STREAM_ERROR
    bounded = " ".join(detail.split())[:300]
    return bounded or _GENERIC_STREAM_ERROR


def _encode_event(event: dict[str, Any]) -> bytes:
    return (json.dumps(event) + "\n").encode("utf-8")


def _validated_progress_event(payload: dict[str, Any]) -> dict[str, Any] | None:
    stage = payload.get("stage")
    done = payload.get("done")
    total = payload.get("total")
    if (
        stage not in _UPLOAD_PROGRESS_STAGES
        or not isinstance(done, int)
        or isinstance(done, bool)
        or not isinstance(total, int)
        or isinstance(total, bool)
        or done < 0
        or total < 0
        or done > total
    ):
        return None
    return {"event": "progress", "stage": stage, "done": done, "total": total}


async def _relay_upload_events(
    response: httpx.Response, pdf_bytes: bytes, organization_id: int
) -> AsyncIterator[bytes]:
    """Re-validate and re-encode each upstream ndjson line before relaying it.

    Progress and error lines are passed through after a shape check; the final
    ``result`` line is re-validated with the same ``UploadSummary`` contract the
    previous buffered proxy enforced, so a compromised or buggy uploader still
    cannot smuggle unexpected fields or an inconsistent byte count to the browser.
    """

    async for raw_line in response.aiter_lines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            yield _encode_event({"event": "error", "detail": _INVALID_UPSTREAM_ERROR})
            return
        event = payload.get("event") if isinstance(payload, dict) else None

        if event == "progress":
            progress = _validated_progress_event(payload)
            if progress is None:
                yield _encode_event(
                    {"event": "error", "detail": _INVALID_UPSTREAM_ERROR}
                )
                return
            yield _encode_event(progress)
            continue

        if event == "error":
            yield _encode_event(
                {"event": "error", "detail": _sanitized_detail(payload.get("detail"))}
            )
            return

        if event == "result":
            try:
                fields = {key: value for key, value in payload.items() if key != "event"}
                summary = UploadSummary.model_validate(fields)
                if summary.byte_count != len(pdf_bytes):
                    raise ValueError("upstream byte count does not match request body")
                summary.check_belongs_to(organization_id)
            except (ValueError, ValidationError, TypeError):
                yield _encode_event(
                    {"event": "error", "detail": _INVALID_UPSTREAM_ERROR}
                )
                return
            yield _encode_event({"event": "result", **summary.model_dump()})
            return

        yield _encode_event({"event": "error", "detail": _INVALID_UPSTREAM_ERROR})
        return


@app.get("/api/documents")
def list_documents(user_id: str) -> list[dict[str, Any]]:
    # Sólo los documentos de la organización del usuario: lo filtra la base (RLS).
    tenant = _tenant_for(user_id)
    try:
        return document_catalog.list_documents(tenant.organization_id)
    except document_catalog.CatalogUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/documents/{document_id}")
def document_details(document_id: str, user_id: str) -> dict[str, Any]:
    tenant = _tenant_for(user_id)
    try:
        selected_id = validate_document_id(document_id)
        details = document_catalog.document_details(selected_id, tenant.organization_id)
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
    user_id: str,
    document_title: str | None = Header(
        default=None,
        alias="X-Document-Title",
        max_length=MAX_ENCODED_TITLE_CHARS,
    ),
) -> StreamingResponse:
    """Proxy one PDF to the internal uploader and relay its ndjson progress stream.

    Content type, declared size and title are still rejected here with their normal
    status codes before any request reaches the uploader. Once the uploader accepts
    the document (its own validation happens before it starts streaming), this relays
    its ``application/x-ndjson`` response line by line, without buffering the whole
    stream, so the browser sees progress as it happens.
    """

    # La organización sale siempre del usuario simulado, nunca del cliente: ni
    # un parámetro extra ni la cabecera interna X-Organization-Id se aceptan.
    if set(request.query_params) - {"user_id"} or ORGANIZATION_HEADER in request.headers:
        raise HTTPException(
            status_code=422,
            detail="La organización la determina el usuario; el cliente no la envía.",
        )
    tenant = _tenant_for(user_id)
    if _declared_mime(request) != PDF_CONTENT_TYPE:
        raise HTTPException(
            status_code=415,
            detail="El tipo de contenido debe ser application/pdf.",
        )
    _reject_known_oversize(request)
    encoded_title = _encoded_title(document_title)
    pdf_bytes = await _bounded_body(request)
    # Salto interno de confianza: el uploader recibe la organización ya resuelta.
    headers = {
        "Content-Type": PDF_CONTENT_TYPE,
        ORGANIZATION_HEADER: str(tenant.organization_id),
    }
    if encoded_title is not None:
        headers["X-Document-Title"] = encoded_title

    client = httpx.AsyncClient(timeout=UPLOADER_TIMEOUT)
    stream_ctx = client.stream("POST", UPLOADER_URL, content=pdf_bytes, headers=headers)
    try:
        response = await stream_ctx.__aenter__()
    except httpx.RequestError as error:
        await client.aclose()
        raise HTTPException(
            status_code=503,
            detail="La carga no está disponible temporalmente.",
        ) from error
    except Exception as error:
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail="El servicio de carga devolvió una respuesta inválida.",
        ) from error

    if response.status_code in {422, 429, 503}:
        try:
            body = await response.aread()
            payload = json.loads(body)
        except ValueError:
            payload = None
        finally:
            await stream_ctx.__aexit__(None, None, None)
            await client.aclose()
        raise HTTPException(
            status_code=response.status_code,
            detail=_upstream_detail(payload, response.status_code),
        )
    if response.status_code != 200:
        await stream_ctx.__aexit__(None, None, None)
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail="El servicio de carga devolvió una respuesta inválida.",
        )

    async def relay() -> AsyncIterator[bytes]:
        try:
            async for chunk in _relay_upload_events(
                response, pdf_bytes, tenant.organization_id
            ):
                yield chunk
        finally:
            await stream_ctx.__aexit__(None, None, None)
            await client.aclose()

    return StreamingResponse(relay(), media_type=NDJSON_CONTENT_TYPE)


@app.post("/api/query", response_model=QueryResponse)
def query(request: QueryRequest) -> dict[str, Any]:
    if request.mode == "text-to-sql" and request.document_id is not None:
        raise HTTPException(
            status_code=422,
            detail="El modo text-to-sql no admite filtro por documento.",
        )
    tenant = _tenant_for(request.user_id)
    try:
        workflow = workflows.WORKFLOWS[request.mode]
        if request.document_id is None:
            result = workflow(request.question, request.top_k, tenant=tenant)
        else:
            result = workflow(
                request.question,
                request.top_k,
                document_id=request.document_id,
                tenant=tenant,
            )
        return {**result, "user": {"id": tenant.user_id, "label": tenant.label}}
    except MissingOpenRouterKey as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except SQLRejected as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except workflows.ServiceUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except OpenRouterError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
