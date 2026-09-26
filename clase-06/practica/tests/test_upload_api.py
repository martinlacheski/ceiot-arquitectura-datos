from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest  # type: ignore[import-not-found]
from fastapi import HTTPException  # type: ignore[import-not-found]
from fastapi.testclient import TestClient  # type: ignore[import-not-found]
from starlette.requests import Request  # type: ignore[import-not-found]

from loader import upload_api  # type: ignore[import-not-found]
from loader.pdf_document import MAX_PDF_BYTES, parse_document  # type: ignore[import-not-found]
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
    "embedding_model": "intfloat/multilingual-e5-small",
    "dimension": 384,
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
    return TestClient(upload_api.app)


def test_health_is_light_and_does_not_touch_ingestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        upload_api.pdf_storage,
        "ingest_document",
        lambda *_args: pytest.fail("health must not initialize ingestion"),
    )

    response = _client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rejects_wrong_mime_before_read_or_ingest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        upload_api.pdf_storage,
        "ingest_document",
        lambda *_args: pytest.fail("wrong MIME must not reach ingestion"),
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
        asyncio.run(upload_api.upload_document(request, None))
    assert captured.value.status_code == 415
    assert receive_calls == 0


def test_content_length_oversize_is_rejected_before_body_read_or_ingest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        upload_api.pdf_storage,
        "ingest_document",
        lambda *_args: pytest.fail("oversize request must not reach ingestion"),
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
        asyncio.run(upload_api.upload_document(request, None))

    assert captured.value.status_code == 413
    assert captured.value.detail == "El PDF supera el límite de 10 MiB."
    assert receive_calls == 0


def test_streaming_limit_rejects_oversize_without_calling_ingest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        upload_api.pdf_storage,
        "ingest_document",
        lambda *_args: pytest.fail("oversize stream must not reach ingestion"),
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
        asyncio.run(upload_api.upload_document(request, None))

    assert captured.value.status_code == 413


def test_bad_pdf_magic_becomes_safe_422(monkeypatch: pytest.MonkeyPatch) -> None:
    def validate_only(pdf_bytes: bytes, title: str, mime: str) -> None:
        parse_document(pdf_bytes, title, mime)

    monkeypatch.setattr(upload_api.pdf_storage, "ingest_document", validate_only)

    response = _client().post(
        "/internal/documents",
        content=b"not a pdf",
        headers={"content-type": "application/pdf"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "El archivo no tiene la firma de un PDF válido."
    }


def test_success_passes_raw_bytes_title_and_mime_and_returns_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[bytes, str, str]] = []

    def ingest(pdf_bytes: bytes, title: str, mime: str) -> dict[str, Any]:
        observed.append((pdf_bytes, title, mime))
        return SUMMARY

    monkeypatch.setattr(upload_api.pdf_storage, "ingest_document", ingest)

    response = _client().post(
        "/internal/documents",
        content=PDF_BYTES,
        headers={
            "content-type": "application/pdf; charset=binary",
            "x-document-title": "Informe de prueba",
        },
    )

    assert response.status_code == 200
    assert response.json() == SUMMARY
    assert response.json()["chunk_count"] == 3
    assert len(response.json()["embedding_preview"]) == 6
    assert observed == [(PDF_BYTES, "Informe de prueba", "application/pdf")]


def test_title_header_is_optional_unicode_decoded_and_raw_ascii_compatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_titles: list[str] = []

    def ingest(_pdf_bytes: bytes, title: str, _mime: str) -> dict[str, Any]:
        observed_titles.append(title)
        return SUMMARY

    monkeypatch.setattr(upload_api.pdf_storage, "ingest_document", ingest)
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
        "ingest_document",
        lambda *_args: pytest.fail("invalid title must not reach ingestion"),
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
def test_service_failures_return_sanitized_503(
    failure: Exception,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: Any) -> dict[str, Any]:
        raise failure

    monkeypatch.setattr(upload_api.pdf_storage, "ingest_document", fail)

    response = _client().post(
        "/internal/documents",
        content=PDF_BYTES,
        headers={"content-type": "application/pdf"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "La carga no está disponible temporalmente."
    }
    assert "password" not in response.text
    assert "secret" not in response.text

    monkeypatch.setattr(upload_api.pdf_storage, "ingest_document", lambda *_: SUMMARY)
    after_failure = _client().post(
        "/internal/documents",
        content=PDF_BYTES,
        headers={"content-type": "application/pdf"},
    )
    assert after_failure.status_code == 200


def test_ingestion_gate_rejects_overlap_and_allows_next_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = threading.Event()
    release = threading.Event()
    responses: dict[str, Any] = {}
    calls = 0

    def ingest(*_args: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            assert release.wait(timeout=5)
        return SUMMARY

    monkeypatch.setattr(upload_api.pdf_storage, "ingest_document", ingest)

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

    assert "image: ceiot-clase-06-python:local" in uploader
    assert "loader.upload_api:app" in uploader
    assert '      - "8007"' in uploader
    assert "    ports:" not in uploader
    assert "RAG_INGEST_POSTGRES_PASSWORD: ceiot_rag_ingest_demo_only" in uploader
    assert "POSTGRES_HOST: postgres" in uploader
    assert 'POSTGRES_PORT: "5432"' in uploader
    assert "POSTGRES_DB" in environment_keys
    assert "SEAWEEDFS_S3_ENDPOINT: http://seaweedfs:8333" in uploader
    assert "MANUAL_BUCKET: ceiot-manuales" in uploader
    assert "MODELO_EMBEDDING: intfloat/multilingual-e5-small" in uploader
    assert "embedding_model_cache:/models/huggingface" in uploader
    assert {"POSTGRES_USER", "POSTGRES_PASSWORD", "OPENROUTER_API_KEY"}.isdisjoint(
        environment_keys
    )
    assert "postgres:\n        condition: service_healthy" in uploader
    assert "seaweedfs:\n        condition: service_healthy" in uploader
    assert "mem_limit: 2g" in uploader
    assert 'cpus: "2.0"' in uploader
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
