from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

import pytest  # type: ignore[import-not-found]
from fastapi import HTTPException  # type: ignore[import-not-found]
from fastapi.testclient import TestClient  # type: ignore[import-not-found]
from starlette.requests import Request  # type: ignore[import-not-found]

from loader import upload_api  # type: ignore[import-not-found]
from loader.pdf_document import (  # type: ignore[import-not-found]
    MAX_PDF_BYTES,
    ParsedDocument,
)
from loader.pdf_storage import UploadUnavailable  # type: ignore[import-not-found]


PDF_BYTES = b"%PDF synthetic API payload"
SUMMARY = {
    "document_id": "upload-0123456789abcdef01234567",
    "version": 1,
    "title": "Informe de prueba",
    "object_key": "uploads/upload-0123456789abcdef01234567/v1/digest.pdf",
    "sha256": "0" * 64,
    "byte_count": len(PDF_BYTES),
    "page_count": 2,
    "extracted_char_count": 321,
    "chunk_count": 3,
    "embedding_model": "BAAI/bge-m3",
    "dimension": 1024,
    "index_status": "indexed",
    "embedding_preview": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
    "trace": [
        "pdf_validated",
        "chunks_embedded",
        "s3_stored",
        "s3_verified",
        "postgres_indexed",
    ],
}


def _client() -> TestClient:
    # La API pública ya tradujo el usuario a su organización: el salto interno la
    # recibe en X-Organization-Id (ver tests/test_tenant_documents.py).
    return TestClient(upload_api.app, headers={"X-Organization-Id": "1"})


def _ndjson_events(response: Any) -> list[dict[str, Any]]:
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def _fail_parse(reason: str):
    def parse(*_args: Any, **_kwargs: Any) -> ParsedDocument:
        pytest.fail(reason)

    return parse


def _fail_stream(reason: str):
    def stream(*_args: Any, **_kwargs: Any) -> Iterator[dict[str, Any]]:
        pytest.fail(reason)
        yield {}  # pragma: no cover - unreachable, keeps this a generator

    return stream


def _events_stream(events: list[dict[str, Any]]):
    def stream(*_args: Any, **_kwargs: Any) -> Iterator[dict[str, Any]]:
        yield from events

    return stream


def _fake_document(title: str) -> ParsedDocument:
    """A stand-in for ``parse_document`` in tests that only exercise routing/streaming.

    ``PDF_BYTES`` above is not a real PDF, so real parsing would reject it; these tests
    patch ``upload_api.parse_document`` with this instead so they can focus on the HTTP
    contract (status codes, title decoding, ndjson framing) without an actual PDF.
    """

    digest = SUMMARY["sha256"]
    return ParsedDocument(
        document_id=SUMMARY["document_id"],
        version=1,
        title=title,
        sha256=digest,
        byte_count=len(PDF_BYTES),
        page_count=2,
        extracted_char_count=321,
        object_key=SUMMARY["object_key"],
        chunks=(),
    )


def _patch_parse_document(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        upload_api,
        "parse_document",
        lambda pdf_bytes, title, content_type, organization_id: _fake_document(title),
    )


def test_health_is_light_and_does_not_touch_ingestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        upload_api, "parse_document", _fail_parse("health must not parse documents")
    )
    monkeypatch.setattr(
        upload_api.pdf_storage,
        "ingest_parsed_document_stream",
        _fail_stream("health must not initialize ingestion"),
    )

    response = _client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rejects_wrong_mime_before_read_or_ingest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        upload_api.pdf_storage,
        "ingest_parsed_document_stream",
        _fail_stream("wrong MIME must not reach ingestion"),
    )

    response = _client().post(
        "/internal/documents",
        content=PDF_BYTES,
        headers={"content-type": "text/plain"},
    )

    assert response.status_code == 415
    assert response.json() == {
        "detail": "El tipo de contenido debe ser application/pdf."
    }

    receive_calls = 0

    async def unread_body() -> dict[str, Any]:
        nonlocal receive_calls
        receive_calls += 1
        raise AssertionError("wrong MIME must not read the request body")

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/documents",
            "headers": [(b"content-type", b"text/plain")],
        },
        unread_body,
    )
    with pytest.raises(HTTPException) as captured:
        asyncio.run(upload_api.upload_document(request, None, "1"))
    assert captured.value.status_code == 415
    assert receive_calls == 0


def test_content_length_oversize_is_rejected_before_body_read_or_ingest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        upload_api.pdf_storage,
        "ingest_parsed_document_stream",
        _fail_stream("oversize request must not reach ingestion"),
    )
    receive_calls = 0

    async def unread_body() -> dict[str, Any]:
        nonlocal receive_calls
        receive_calls += 1
        raise AssertionError("request body must not be read")

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/documents",
            "headers": [
                (b"content-type", b"application/pdf"),
                (b"content-length", str(MAX_PDF_BYTES + 1).encode("ascii")),
            ],
        },
        unread_body,
    )

    with pytest.raises(HTTPException) as captured:
        asyncio.run(upload_api.upload_document(request, None, "1"))

    assert captured.value.status_code == 413
    assert captured.value.detail == "El PDF supera el límite de 50 MiB."
    assert receive_calls == 0


def test_streaming_limit_rejects_oversize_without_calling_ingest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        upload_api.pdf_storage,
        "ingest_parsed_document_stream",
        _fail_stream("oversize stream must not reach ingestion"),
    )
    sent = False

    async def chunked_body() -> dict[str, Any]:
        nonlocal sent
        if not sent:
            sent = True
            return {
                "type": "http.request",
                "body": b"x" * (MAX_PDF_BYTES + 1),
                "more_body": False,
            }
        return {"type": "http.disconnect"}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/documents",
            "headers": [(b"content-type", b"application/pdf")],
        },
        chunked_body,
    )

    with pytest.raises(HTTPException) as captured:
        asyncio.run(upload_api.upload_document(request, None, "1"))

    assert captured.value.status_code == 413


def test_bad_pdf_magic_becomes_safe_422(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        upload_api.pdf_storage,
        "ingest_parsed_document_stream",
        _fail_stream("rejected PDFs must not reach ingestion"),
    )

    response = _client().post(
        "/internal/documents",
        content=b"not a pdf",
        headers={"content-type": "application/pdf"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "El archivo no tiene la firma de un PDF válido."
    }


def test_success_streams_progress_then_a_final_result_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_parse_document(monkeypatch)
    observed: list[tuple[bytes, str]] = []

    def stream(
        document: ParsedDocument, pdf_bytes: bytes, organization_id: int
    ) -> Iterator[dict[str, Any]]:
        assert organization_id == 1
        observed.append((pdf_bytes, document.title))
        yield {"event": "progress", "stage": "pdf_validated", "done": 0, "total": 3}
        yield {"event": "progress", "stage": "chunks_embedded", "done": 3, "total": 3}
        yield {"event": "result", **SUMMARY}

    monkeypatch.setattr(upload_api.pdf_storage, "ingest_parsed_document_stream", stream)

    response = _client().post(
        "/internal/documents",
        content=PDF_BYTES,
        headers={
            "content-type": "application/pdf; charset=binary",
            "x-document-title": "Informe de prueba",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = _ndjson_events(response)
    assert events[0] == {"event": "progress", "stage": "pdf_validated", "done": 0, "total": 3}
    assert events[-1] == {"event": "result", **SUMMARY}
    assert events[-1]["chunk_count"] == 3
    assert len(events[-1]["embedding_preview"]) == 6
    assert observed == [(PDF_BYTES, "Informe de prueba")]


def test_title_header_is_optional_unicode_decoded_and_raw_ascii_compatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_parse_document(monkeypatch)
    observed_titles: list[str] = []

    def stream(
        document: ParsedDocument, _pdf_bytes: bytes, _organization_id: int
    ) -> Iterator[dict[str, Any]]:
        observed_titles.append(document.title)
        yield {"event": "result", **SUMMARY}

    monkeypatch.setattr(upload_api.pdf_storage, "ingest_parsed_document_stream", stream)
    client = _client()
    unicode_title = "Informe térmico ñ.pdf"

    defaulted = client.post(
        "/internal/documents",
        content=PDF_BYTES,
        headers={"content-type": "application/pdf"},
    )
    raw_ascii = client.post(
        "/internal/documents",
        content=PDF_BYTES,
        headers={
            "content-type": "application/pdf",
            "x-document-title": "Informe ASCII.pdf",
        },
    )
    unicode_encoded = client.post(
        "/internal/documents",
        content=PDF_BYTES,
        headers={
            "content-type": "application/pdf",
            "x-document-title": quote(unicode_title, safe=""),
        },
    )

    assert defaulted.status_code == raw_ascii.status_code == unicode_encoded.status_code == 200
    assert observed_titles == ["Documento PDF", "Informe ASCII.pdf", unicode_title]


@pytest.mark.parametrize(
    "encoded_title",
    ["%", "%GG", "%FF", quote("x" * 201, safe=""), "x" * 1201],
)
def test_title_rejects_invalid_percent_utf8_decoded_length_and_encoded_length(
    encoded_title: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        upload_api.pdf_storage,
        "ingest_parsed_document_stream",
        _fail_stream("invalid title must not reach ingestion"),
    )

    response = _client().post(
        "/internal/documents",
        content=PDF_BYTES,
        headers={
            "content-type": "application/pdf",
            "x-document-title": encoded_title,
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize("failure", [UploadUnavailable(), RuntimeError("password=secret")])
def test_service_failures_after_streaming_starts_become_a_sanitized_error_event(
    failure: Exception,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_parse_document(monkeypatch)

    def fail(*_args: Any) -> Iterator[dict[str, Any]]:
        raise failure
        yield {}  # pragma: no cover - unreachable, keeps this a generator

    monkeypatch.setattr(upload_api.pdf_storage, "ingest_parsed_document_stream", fail)

    response = _client().post(
        "/internal/documents",
        content=PDF_BYTES,
        headers={"content-type": "application/pdf"},
    )

    # Validation already passed by the time ingestion runs, so the stream still opens
    # with 200; the failure surfaces as a final ndjson error event instead.
    assert response.status_code == 200
    events = _ndjson_events(response)
    assert events == [{"event": "error", "detail": "La carga no está disponible temporalmente."}]
    assert "password" not in response.text
    assert "secret" not in response.text

    monkeypatch.setattr(
        upload_api.pdf_storage,
        "ingest_parsed_document_stream",
        _events_stream([{"event": "result", **SUMMARY}]),
    )
    after_failure = _client().post(
        "/internal/documents",
        content=PDF_BYTES,
        headers={"content-type": "application/pdf"},
    )
    assert after_failure.status_code == 200
    assert _ndjson_events(after_failure)[-1] == {"event": "result", **SUMMARY}


def test_ingestion_gate_rejects_overlap_and_allows_next_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_parse_document(monkeypatch)
    entered = threading.Event()
    release = threading.Event()
    responses: dict[str, Any] = {}
    calls = 0

    def stream(*_args: Any) -> Iterator[dict[str, Any]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            assert release.wait(timeout=5)
        yield {"event": "result", **SUMMARY}

    monkeypatch.setattr(upload_api.pdf_storage, "ingest_parsed_document_stream", stream)

    def first_request() -> None:
        responses["first"] = _client().post(
            "/internal/documents",
            content=PDF_BYTES,
            headers={"content-type": "application/pdf"},
        )

    first_thread = threading.Thread(target=first_request)
    first_thread.start()
    assert entered.wait(timeout=5)

    overlapping = _client().post(
        "/internal/documents",
        content=PDF_BYTES,
        headers={"content-type": "application/pdf"},
    )
    release.set()
    first_thread.join(timeout=5)
    assert not first_thread.is_alive()

    sequential = _client().post(
        "/internal/documents",
        content=PDF_BYTES,
        headers={"content-type": "application/pdf"},
    )

    assert responses["first"].status_code == 200
    assert overlapping.status_code == 429
    assert sequential.status_code == 200
    assert calls == 2


def test_uploader_compose_service_is_internal_bounded_and_least_privileged() -> None:
    compose = (Path(__file__).resolve().parents[1] / "compose.yaml").read_text(
        encoding="utf-8"
    )
    uploader = compose.split("\n  uploader:\n", 1)[1].split("\n  app:\n", 1)[0]
    environment = uploader.split("    environment:\n", 1)[1].split(
        "    volumes:\n", 1
    )[0]
    environment_keys = {
        line.strip().split(":", 1)[0]
        for line in environment.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "image: ceiot-clase-07-python:local" in uploader
    assert "loader.upload_api:app" in uploader
    assert '      - "8007"' in uploader
    assert "    ports:" not in uploader
    assert "RAG_INGEST_POSTGRES_PASSWORD: ceiot_rag_ingest_demo_only" in uploader
    assert "POSTGRES_HOST: postgres" in uploader
    assert 'POSTGRES_PORT: "5432"' in uploader
    assert "POSTGRES_DB" in environment_keys
    assert "SEAWEEDFS_S3_ENDPOINT: http://seaweedfs:8333" in uploader
    assert "MANUAL_BUCKET: ${MANUAL_BUCKET:-ceiot-manuales}" in uploader
    assert "MODELO_EMBEDDING: ${MODELO_EMBEDDING:-BAAI/bge-m3}" in uploader
    # Los hilos de PyTorch deben coincidir con las CPU asignadas al servicio.
    assert 'cpus: "${UPLOADER_CPUS:-2}"' in uploader
    assert 'OMP_NUM_THREADS: "${UPLOADER_CPUS:-2}"' in uploader
    assert "embedding_model_cache:/models/huggingface" in uploader
    assert {"POSTGRES_USER", "POSTGRES_PASSWORD", "OPENROUTER_API_KEY"}.isdisjoint(
        environment_keys
    )
    assert "postgres:\n        condition: service_healthy" in uploader
    assert "seaweedfs:\n        condition: service_healthy" in uploader
    assert "mem_limit: ${UPLOADER_MEM_LIMIT:-4g}" in uploader
    assert "pids_limit: 256" in uploader
    assert "http://127.0.0.1:8007/health" in uploader
    assert "profiles:" not in uploader


def test_app_compose_service_remains_read_only() -> None:
    compose = (Path(__file__).resolve().parents[1] / "compose.yaml").read_text(
        encoding="utf-8"
    )
    app_block = compose.split("\n  app:\n", 1)[1].split("\n  seaweedfs:\n", 1)[0]
    environment = app_block.split("    environment:\n", 1)[1].split(
        "    volumes:\n", 1
    )[0]
    environment_keys = {
        line.strip().split(":", 1)[0]
        for line in environment.splitlines()
        if line.strip()
    }

    assert "RAG_POSTGRES_USER: rag_readonly" in environment
    assert "AI_POSTGRES_USER: ai_readonly" in environment
    assert "RAG_INGEST_POSTGRES_PASSWORD" not in environment_keys
    assert "POSTGRES_USER" not in environment_keys
    assert "POSTGRES_PASSWORD" not in environment_keys
