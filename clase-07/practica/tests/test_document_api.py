from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx  # type: ignore[import-not-found]
import pytest  # type: ignore[import-not-found]
from fastapi import HTTPException  # type: ignore[import-not-found]
from fastapi.testclient import TestClient  # type: ignore[import-not-found]
from starlette.requests import Request  # type: ignore[import-not-found]

from api import web_app, workflows  # type: ignore[import-not-found]
from api.web_app import upload_document  # type: ignore[import-not-found]
from loader.pdf_document import MAX_PDF_BYTES  # type: ignore[import-not-found]
from shared import document_catalog  # type: ignore[import-not-found]
from shared.document_catalog import CatalogUnavailable  # type: ignore[import-not-found]
from shared.document_identity import derive_document_id, object_key_for  # type: ignore[import-not-found]
from shared.tenants import resolve_user  # type: ignore[import-not-found]

ANA = resolve_user("ana")

_HTTPX_ASYNC_CLIENT = httpx.AsyncClient
PDF_BYTES = b"%PDF bounded public proxy"
PDF_SHA256 = "54143acde2a0a647326a3faf759b32776512dfa62970e5830d1467cf24787fb4"
# La identidad depende del contenido y de la organización (Ana = organización 1).
DOCUMENT_ID = derive_document_id(1, PDF_SHA256)
SUMMARY = {
    "document_id": DOCUMENT_ID,
    "version": 1,
    "title": "Informe térmico ñ",
    "object_key": object_key_for(1, DOCUMENT_ID, PDF_SHA256),
    "sha256": PDF_SHA256,
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
    client = TestClient(web_app.app)
    # Todas las rutas de documentos exigen el usuario simulado (user_id).
    client.params = {"user_id": "ana"}
    return client


def _ndjson_events(response: Any) -> list[dict[str, Any]]:
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def _ndjson_body(events: list[dict[str, Any]]) -> bytes:
    return "".join(json.dumps(event) + "\n" for event in events).encode("utf-8")


def _ndjson_response(events: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(
        200,
        content=_ndjson_body(events),
        headers={"content-type": "application/x-ndjson"},
    )


def _install_proxy(monkeypatch: pytest.MonkeyPatch, handler: httpx.MockTransport) -> None:
    class FakeAsyncClient(_HTTPX_ASYNC_CLIENT):
        def __init__(self, **kwargs: Any) -> None:
            timeout = kwargs["timeout"]
            assert isinstance(timeout, httpx.Timeout)
            assert timeout.connect == pytest.approx(10.0)
            assert timeout.write == pytest.approx(30.0)
            assert timeout.read == pytest.approx(120.0)
            assert timeout.pool == pytest.approx(10.0)
            super().__init__(transport=handler, timeout=timeout)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)


def test_catalog_routes_list_details_not_found_bad_id_and_sanitized_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = {"document_id": DOCUMENT_ID, "title": "Informe", "status": "indexed"}
    details = {**summary, "chunks": []}
    monkeypatch.setattr(document_catalog, "list_documents", lambda organization_id: [summary])
    monkeypatch.setattr(
        document_catalog,
        "document_details",
        lambda document_id, organization_id: (
            details if document_id == DOCUMENT_ID and organization_id == 1 else None
        ),
    )
    client = _client()

    assert client.get("/api/documents").json() == [summary]
    assert client.get(f"/api/documents/{DOCUMENT_ID}").json() == details
    assert client.get("/api/documents/upload-aaaaaaaaaaaaaaaaaaaaaaaa").status_code == 404
    assert client.get("/api/documents/not-valid").status_code == 422

    def unavailable(organization_id: int) -> list[dict[str, Any]]:
        raise CatalogUnavailable()

    monkeypatch.setattr(document_catalog, "list_documents", unavailable)
    response = client.get("/api/documents")
    assert response.status_code == 503
    assert response.json() == {
        "detail": "El catálogo de documentos no está disponible temporalmente."
    }


def test_query_filter_is_keyword_only_for_rag_and_integrated_and_legacy_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    expected = {"answer": "ok", "sql": None, "rows": [], "sources": [], "trace": []}

    def workflow(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append((args, kwargs))
        return expected

    monkeypatch.setitem(workflows.WORKFLOWS, "rag", workflow)
    monkeypatch.setitem(workflows.WORKFLOWS, "integrated", workflow)
    client = _client()

    assert client.post(
        "/api/query",
        json={"question": "Pregunta válida", "mode": "rag", "document_id": DOCUMENT_ID, "user_id": "ana"},
    ).status_code == 200
    assert client.post(
        "/api/query",
        json={
            "question": "Pregunta válida",
            "mode": "integrated",
            "document_id": DOCUMENT_ID,
            "user_id": "ana",
        },
    ).status_code == 200
    assert client.post(
        "/api/query", json={"question": "Pregunta válida", "mode": "integrated", "user_id": "ana"}
    ).status_code == 200

    assert calls == [
        (("Pregunta válida", 4), {"document_id": DOCUMENT_ID, "tenant": ANA}),
        (("Pregunta válida", 4), {"document_id": DOCUMENT_ID, "tenant": ANA}),
        (("Pregunta válida", 4), {"tenant": ANA}),
    ]


def test_text_to_sql_rejects_document_filter_before_openrouter_and_bad_id_is_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        workflows.WORKFLOWS,
        "text-to-sql",
        lambda *_args, **_kwargs: pytest.fail("OpenRouter workflow must not run"),
    )
    client = _client()

    filtered = client.post(
        "/api/query",
        json={
            "question": "Promedio de CO2",
            "mode": "text-to-sql",
            "document_id": DOCUMENT_ID,
            "user_id": "ana",
        },
    )
    invalid = client.post(
        "/api/query",
        json={"question": "Pregunta válida", "mode": "rag", "document_id": "bad", "user_id": "ana"},
    )

    assert filtered.status_code == 422
    assert "text-to-sql" in filtered.json()["detail"]
    assert invalid.status_code == 422


def test_public_upload_streams_progress_then_result_for_fixed_internal_url_with_unicode_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[httpx.Request] = []
    upstream_events = [
        {"event": "progress", "stage": "pdf_validated", "done": 0, "total": 3},
        {"event": "progress", "stage": "chunks_embedded", "done": 3, "total": 3},
        {"event": "progress", "stage": "s3_stored", "done": 3, "total": 3},
        {"event": "progress", "stage": "s3_verified", "done": 3, "total": 3},
        {"event": "progress", "stage": "postgres_indexed", "done": 3, "total": 3},
        {"event": "result", **SUMMARY},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return _ndjson_response(upstream_events)

    _install_proxy(monkeypatch, httpx.MockTransport(handler))
    title = "Informe térmico ñ.pdf"
    response = _client().post(
        "/api/documents",
        content=PDF_BYTES,
        headers={
            "content-type": "application/pdf",
            "x-document-title": quote(title, safe=""),
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = _ndjson_events(response)
    assert events[:-1] == upstream_events[:-1]
    assert events[-1] == {"event": "result", **SUMMARY}
    assert len(observed) == 1
    request = observed[0]
    assert str(request.url) == "http://uploader:8007/internal/documents"
    assert request.content == PDF_BYTES
    assert request.headers["content-type"] == "application/pdf"
    assert request.headers["x-document-title"] == quote(title, safe="")
    assert "authorization" not in request.headers
    assert "title" not in request.url.params


def test_public_upload_rejects_mime_length_stream_and_title_before_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NoProxy:
        def __init__(self, **_kwargs: Any) -> None:
            pytest.fail("invalid upload must not create proxy client")

    monkeypatch.setattr(httpx, "AsyncClient", NoProxy)
    client = _client()
    assert client.post(
        "/api/documents", content=PDF_BYTES, headers={"content-type": "text/plain"}
    ).status_code == 415
    assert client.post(
        "/api/documents",
        content=b"x",
        headers={
            "content-type": "application/pdf",
            "content-length": str(MAX_PDF_BYTES + 1),
        },
    ).status_code == 413
    assert client.post(
        "/api/documents",
        content=PDF_BYTES,
        headers={"content-type": "application/pdf", "x-document-title": "%FF"},
    ).status_code == 422
    assert client.post(
        "/api/documents",
        content=PDF_BYTES,
        headers={"content-type": "application/pdf", "x-document-title": quote("x" * 201)},
    ).status_code == 422

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
            "path": "/api/documents",
            "query_string": b"user_id=ana",
            "headers": [(b"content-type", b"application/pdf")],
        },
        chunked_body,
    )
    with pytest.raises(HTTPException) as captured:
        asyncio.run(upload_document(request, "ana", None))
    assert captured.value.status_code == 413


@pytest.mark.parametrize(
    ("upstream_status", "expected_status"),
    [(422, 422), (429, 429), (503, 503), (418, 502)],
)
def test_public_upload_maps_only_bounded_upstream_statuses(
    upstream_status: int,
    expected_status: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detail = "x" * 600
    _install_proxy(
        monkeypatch,
        httpx.MockTransport(lambda _request: httpx.Response(upstream_status, json={"detail": detail})),
    )

    response = _client().post(
        "/api/documents", content=PDF_BYTES, headers={"content-type": "application/pdf"}
    )

    assert response.status_code == expected_status
    assert len(response.json()["detail"]) <= 300
    if expected_status == 502:
        assert detail[:20] not in response.text


def test_public_upload_rejects_unknown_missing_and_non_object_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for payload in [{"secret": "upstream-credential"}, {}, ["upstream-credential"]]:
        _install_proxy(
            monkeypatch,
            httpx.MockTransport(lambda _request, payload=payload: _ndjson_response([payload])),
        )

        response = _client().post(
            "/api/documents", content=PDF_BYTES, headers={"content-type": "application/pdf"}
        )

        # The stream already opened with 200 by the time this line is checked, so an
        # unrecognized/incoherent upstream line becomes a final error *event*, not an
        # HTTP error status.
        assert response.status_code == 200
        events = _ndjson_events(response)
        assert events == [
            {
                "event": "error",
                "detail": "El servicio de carga devolvió una respuesta inválida.",
            }
        ]
        assert "secret" not in response.text
        assert "credential" not in response.text


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("document_id", "upload-aaaaaaaaaaaaaaaaaaaaaaaa"),
        ("object_key", "uploads/wrong/v1/secret.pdf"),
        ("sha256", "f" * 64),
        ("embedding_preview", [0.1, 0.2, float("nan"), 0.4, 0.5, 0.6]),
        ("page_count", 0),
        ("chunk_count", 0),
        ("dimension", 768),
        ("byte_count", len(PDF_BYTES) + 1),
    ],
)
def test_public_upload_rejects_incoherent_or_out_of_contract_success(
    field: str,
    invalid_value: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"event": "result", **SUMMARY, field: invalid_value}
    _install_proxy(
        monkeypatch,
        httpx.MockTransport(lambda _request: _ndjson_response([payload])),
    )

    response = _client().post(
        "/api/documents", content=PDF_BYTES, headers={"content-type": "application/pdf"}
    )

    assert response.status_code == 200
    events = _ndjson_events(response)
    assert events == [
        {
            "event": "error",
            "detail": "El servicio de carga devolvió una respuesta inválida.",
        }
    ]
    assert "secret" not in response.text
    assert PDF_SHA256 not in response.text


def test_public_upload_transport_and_invalid_success_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_proxy(
        monkeypatch,
        httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ConnectError("secret host", request=request))),
    )
    response = _client().post(
        "/api/documents", content=PDF_BYTES, headers={"content-type": "application/pdf"}
    )
    assert response.status_code == 503
    assert "secret" not in response.text

    _install_proxy(
        monkeypatch,
        httpx.MockTransport(
            lambda _request: httpx.Response(
                200, content=b"not-json", headers={"content-type": "application/x-ndjson"}
            )
        ),
    )
    response = _client().post(
        "/api/documents", content=PDF_BYTES, headers={"content-type": "application/pdf"}
    )
    assert response.status_code == 200
    events = _ndjson_events(response)
    assert events == [
        {
            "event": "error",
            "detail": "El servicio de carga devolvió una respuesta inválida.",
        }
    ]
    assert "not-json" not in response.text


def test_public_upload_relays_a_mid_stream_error_event_with_bounded_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The uploader only ever emits already-sanitized Spanish error text (see
    # loader.upload_api._stream_error_detail); the proxy's job here is just to keep
    # relaying it as a stream event (not turn it into an HTTP error status, since 200
    # already started) and to bound its length defensively.
    long_detail = "La carga no está disponible temporalmente. " + "x" * 400
    _install_proxy(
        monkeypatch,
        httpx.MockTransport(
            lambda _request: _ndjson_response(
                [
                    {"event": "progress", "stage": "pdf_validated", "done": 0, "total": 3},
                    {"event": "error", "detail": long_detail},
                ]
            )
        ),
    )

    response = _client().post(
        "/api/documents", content=PDF_BYTES, headers={"content-type": "application/pdf"}
    )

    assert response.status_code == 200
    events = _ndjson_events(response)
    assert events[0] == {"event": "progress", "stage": "pdf_validated", "done": 0, "total": 3}
    assert events[1]["event"] == "error"
    assert len(events[1]["detail"]) <= 300


def test_app_compose_depends_on_healthy_uploader_without_writer_credentials() -> None:
    compose = (Path(__file__).resolve().parents[1] / "compose.yaml").read_text(encoding="utf-8")
    app_block = compose.split("\n  app:\n", 1)[1].split("\n  seaweedfs:\n", 1)[0]
    environment = app_block.split("    environment:\n", 1)[1].split("    volumes:\n", 1)[0]
    environment_keys = {
        line.strip().split(":", 1)[0]
        for line in environment.splitlines()
        if line.strip()
    }

    assert "uploader:\n        condition: service_healthy" in app_block
    assert "RAG_POSTGRES_USER: rag_readonly" in environment
    assert "AI_POSTGRES_USER: ai_readonly" in environment
    assert "RAG_INGEST_POSTGRES_PASSWORD" not in environment_keys
    assert "POSTGRES_USER" not in environment_keys
    assert "POSTGRES_PASSWORD" not in environment_keys
