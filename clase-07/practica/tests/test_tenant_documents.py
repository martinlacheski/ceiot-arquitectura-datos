"""Documentos, RAG y Redis por organización (tenant).

Las pruebas con base y Redis reales corren dentro del contenedor ``loader``; el
resto usa dobles de prueba y no necesita infraestructura.
"""

from __future__ import annotations

import io
import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx  # type: ignore[import-not-found]
import psycopg  # type: ignore[import-not-found]
import pytest  # type: ignore[import-not-found]
import redis  # type: ignore[import-not-found]
from fastapi.testclient import TestClient  # type: ignore[import-not-found]
from reportlab.pdfgen import canvas  # type: ignore[import-not-found]

from api import web_app, workflows  # type: ignore[import-not-found]
from api.openrouter_client import OpenRouterClient  # type: ignore[import-not-found]
from loader import pdf_storage, seed_services, upload_api  # type: ignore[import-not-found]
from loader.pdf_document import (  # type: ignore[import-not-found]
    PageChunk,
    ParsedDocument,
    parse_document,
)
from shared import document_catalog, rag_connection  # type: ignore[import-not-found]
from shared.document_identity import (  # type: ignore[import-not-found]
    derive_document_id,
    object_key_for,
)
from shared.tenants import Tenant, resolve_user  # type: ignore[import-not-found]

ROOT = Path(__file__).resolve().parents[1]
ANA = resolve_user("ana")
BRUNO = resolve_user("bruno")
SHA = "ab" * 32


def _pdf_bytes(text: str) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output)
    line = document.beginText(50, 790)
    line.textLine(text)
    document.drawText(line)
    document.showPage()
    document.save()
    return output.getvalue()


# --- identidad del documento por organización ------------------------------------


def test_same_bytes_in_two_tenants_give_two_independent_documents() -> None:
    ana = derive_document_id(1, SHA)
    bruno = derive_document_id(2, SHA)

    assert ana != bruno
    assert object_key_for(1, ana, SHA) != object_key_for(2, bruno, SHA)


def test_same_bytes_in_the_same_tenant_keep_deduplicating() -> None:
    assert derive_document_id(1, SHA) == derive_document_id(1, SHA)


def test_document_id_keeps_the_public_format_and_the_key_has_a_tenant_prefix() -> None:
    document_id = derive_document_id(7, SHA)

    assert re.fullmatch(r"upload-[0-9a-f]{24}", document_id)
    assert object_key_for(7, document_id, SHA) == f"uploads/org-7/{document_id}/v1/{SHA}.pdf"


@pytest.mark.parametrize("bad", [0, -1, "1", None, True, 1.5])
def test_identity_rejects_invalid_organizations(bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        derive_document_id(bad, SHA)  # type: ignore[arg-type]


def test_parse_document_derives_identity_from_content_and_organization() -> None:
    pdf = _pdf_bytes("Procedimiento de calibración del sensor de temperatura ambiente.")

    ana = parse_document(pdf, "Manual", "application/pdf", 1)
    bruno = parse_document(pdf, "Manual", "application/pdf", 2)
    again = parse_document(pdf, "Manual", "application/pdf", 1)

    assert ana.sha256 == bruno.sha256
    assert ana.document_id != bruno.document_id
    assert ana.document_id == again.document_id
    assert ana.object_key.startswith("uploads/org-1/")
    assert bruno.object_key.startswith("uploads/org-2/")
    assert all(chunk.object_key == bruno.object_key for chunk in bruno.chunks)
    assert all(chunk.document_id == bruno.document_id for chunk in bruno.chunks)


def test_parse_document_requires_an_organization() -> None:
    with pytest.raises(TypeError):
        parse_document(_pdf_bytes("texto"), "Manual", "application/pdf")  # type: ignore[call-arg]
    with pytest.raises((TypeError, ValueError)):
        parse_document(_pdf_bytes("texto"), "Manual", "application/pdf", 0)


# --- el uploader escribe bajo el contexto del tenant ------------------------------


class _RecordingCursor:
    def __init__(self, connection: _RecordingConnection) -> None:
        self.connection = connection
        self.rowcount = 1
        self._row: tuple[Any, ...] | None = None

    def __enter__(self) -> _RecordingCursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        normalized = " ".join(sql.split())
        self.connection.executions.append((normalized, params))
        if normalized.startswith("INSERT INTO manual_documents"):
            self._row = (params[5], params[2])

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


class _RecordingConnection:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[Any, ...]]] = []
        self.committed = False

    def cursor(self) -> _RecordingCursor:
        return _RecordingCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        return None


def _parsed(organization_id: int) -> ParsedDocument:
    document_id = derive_document_id(organization_id, SHA)
    object_key = object_key_for(organization_id, document_id, SHA)
    chunk = PageChunk(
        document_id=document_id,
        version=1,
        page=1,
        section="Página 1",
        chunk_index=0,
        content="Contenido significativo del fragmento.",
        object_key=object_key,
    )
    return ParsedDocument(
        document_id=document_id,
        version=1,
        title="Informe",
        sha256=SHA,
        byte_count=10,
        page_count=1,
        extracted_char_count=38,
        object_key=object_key,
        chunks=(chunk,),
    )


def test_persist_sets_the_tenant_first_and_writes_the_organization_on_every_row() -> None:
    connection = _RecordingConnection()

    pdf_storage._persist_document(connection, _parsed(2), [[0.1] * 1024], 2)

    first_sql, first_params = connection.executions[0]
    assert "set_config('app.tenant_id'" in first_sql and "true" in first_sql
    assert first_params == ("2",)
    inserts = [
        (sql, params)
        for sql, params in connection.executions
        if sql.startswith("INSERT INTO manual_")
    ]
    assert len(inserts) == 2
    for sql, params in inserts:
        assert "organization_id" in sql
        assert params[-1] == 2
    assert connection.committed


@pytest.mark.parametrize("bad", [0, -3, "2", None, True])
def test_persist_rejects_an_invalid_organization_before_touching_the_database(
    bad: object,
) -> None:
    connection = _RecordingConnection()

    with pytest.raises((TypeError, ValueError)):
        pdf_storage._persist_document(connection, _parsed(1), [[0.1] * 1024], bad)  # type: ignore[arg-type]

    assert connection.executions == []


def _uploader_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, list[Any]]:
    seen: list[Any] = []

    def parse(pdf: bytes, title: str, content_type: str, organization_id: int) -> ParsedDocument:
        seen.append(("parse", organization_id))
        return _parsed(organization_id)

    def stream(document: ParsedDocument, pdf: bytes, organization_id: int) -> Iterator[dict[str, Any]]:
        seen.append(("stream", organization_id))
        yield {"event": "progress", "stage": "pdf_validated", "done": 0, "total": 1}

    monkeypatch.setattr(upload_api, "parse_document", parse)
    monkeypatch.setattr(pdf_storage, "ingest_parsed_document_stream", stream)
    return TestClient(upload_api.app), seen


def _post_pdf(client: TestClient, headers: dict[str, str]) -> httpx.Response:
    return client.post(
        "/internal/documents",
        content=b"%PDF-1.4 fixture",
        headers={"Content-Type": "application/pdf", **headers},
    )


def test_uploader_requires_the_organization_header(monkeypatch: pytest.MonkeyPatch) -> None:
    client, seen = _uploader_client(monkeypatch)

    response = _post_pdf(client, {})

    assert response.status_code == 422
    assert seen == []


@pytest.mark.parametrize("bad", ["0", "-1", "abc", "1.5", "", " ", "1; DROP", "01"])
def test_uploader_rejects_an_invalid_organization(
    monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    client, seen = _uploader_client(monkeypatch)

    response = _post_pdf(client, {"X-Organization-Id": bad})

    assert response.status_code == 422
    assert seen == []


def test_uploader_passes_the_organization_to_parsing_and_ingestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, seen = _uploader_client(monkeypatch)

    response = _post_pdf(client, {"X-Organization-Id": "2"})

    assert response.status_code == 200
    assert seen == [("parse", 2), ("stream", 2)]


# --- la API pública resuelve usuario -> tenant y nunca acepta una organización ----


def _summary(organization_id: int) -> dict[str, Any]:
    document_id = derive_document_id(organization_id, SHA)
    return {
        "event": "result",
        "document_id": document_id,
        "version": 1,
        "title": "Informe",
        "object_key": object_key_for(organization_id, document_id, SHA),
        "sha256": SHA,
        "byte_count": 16,
        "page_count": 1,
        "extracted_char_count": 40,
        "chunk_count": 1,
        "embedding_model": "BAAI/bge-m3",
        "dimension": 1024,
        "index_status": "indexed",
        "embedding_preview": [0.1] * 6,
        "trace": [
            "pdf_validated",
            "chunks_embedded",
            "s3_stored",
            "s3_verified",
            "postgres_indexed",
        ],
    }


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _proxy_to_uploader(
    monkeypatch: pytest.MonkeyPatch, result: dict[str, Any]
) -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            content=(json.dumps(result) + "\n").encode(),
            headers={"content-type": "application/x-ndjson"},
        )

    class FakeAsyncClient(_REAL_ASYNC_CLIENT):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(transport=httpx.MockTransport(handler), timeout=kwargs["timeout"])

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    return requests


def _upload(params: dict[str, str], headers: dict[str, str] | None = None) -> httpx.Response:
    return TestClient(web_app.app).post(
        "/api/documents",
        params=params,
        content=b"%PDF-1.4 fixture",
        headers={"Content-Type": "application/pdf", **(headers or {})},
    )


@pytest.mark.parametrize(("user", "organization"), [("ana", "1"), ("bruno", "2")])
def test_upload_resolves_the_user_to_its_organization_for_the_uploader(
    monkeypatch: pytest.MonkeyPatch, user: str, organization: str
) -> None:
    requests = _proxy_to_uploader(monkeypatch, _summary(int(organization)))

    response = _upload({"user_id": user})

    assert response.status_code == 200
    assert json.loads(response.text.splitlines()[-1])["event"] == "result"
    assert requests[0].headers["X-Organization-Id"] == organization


def test_upload_requires_a_known_user(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _proxy_to_uploader(monkeypatch, _summary(1))

    assert _upload({}).status_code == 422
    assert _upload({"user_id": "mallory"}).status_code == 422
    assert requests == []


@pytest.mark.parametrize("name", ["organization_id", "tenant_id"])
def test_upload_rejects_an_organization_sent_by_the_client(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    requests = _proxy_to_uploader(monkeypatch, _summary(2))

    assert _upload({"user_id": "ana", name: "2"}).status_code == 422
    assert _upload({"user_id": "ana"}, {"X-Organization-Id": "2"}).status_code == 422
    assert requests == []


def test_upload_rejects_a_result_that_belongs_to_another_organization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _proxy_to_uploader(monkeypatch, _summary(2))

    response = _upload({"user_id": "ana"})

    last = json.loads(response.text.splitlines()[-1])
    assert last["event"] == "error"


def test_catalog_routes_require_a_user_and_query_with_its_organization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, tuple[Any, ...]]] = []
    monkeypatch.setattr(
        document_catalog,
        "list_documents",
        lambda organization_id: calls.append(("list", (organization_id,))) or [],
    )
    monkeypatch.setattr(
        document_catalog,
        "document_details",
        lambda document_id, organization_id: calls.append(("details", (document_id, organization_id)))
        or None,
    )
    client = TestClient(web_app.app)
    document_id = derive_document_id(1, SHA)

    assert client.get("/api/documents").status_code == 422
    assert client.get("/api/documents", params={"user_id": "mallory"}).status_code == 422
    assert client.get(f"/api/documents/{document_id}").status_code == 422
    assert client.get("/api/documents", params={"user_id": "bruno"}).status_code == 200
    assert client.get(f"/api/documents/{document_id}", params={"user_id": "bruno"}).status_code == 404
    assert calls == [("list", (2,)), ("details", (document_id, 2))]


# --- recuperación RAG: el tenant se fija antes de buscar vecinos -------------------


class _Chat(OpenRouterClient):
    def __init__(self) -> None:  # noqa: D107
        self.calls = 0

    def chat(self, messages: list[dict[str, str]], *, max_completion_tokens: int) -> str:
        self.calls += 1
        return "respuesta"


def test_retrieval_sets_the_tenant_in_the_same_transaction_before_searching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log: list[str] = []

    class Cursor:
        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def execute(self, sql: str, params: Any = None) -> None:
            log.append(" ".join(sql.split()) + f" {params}")

    class Connection:
        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def cursor(self) -> Cursor:
            return Cursor()

        def transaction(self) -> Connection:
            log.append("BEGIN")
            return self

    class Model:
        def encode(self, *_args: Any, **_kwargs: Any) -> list[float]:
            return [0.0] * 1024

    monkeypatch.setattr(rag_connection.psycopg, "connect", lambda **_: Connection())
    monkeypatch.setattr(rag_connection, "rag_connection_settings", lambda: {})
    monkeypatch.setattr(workflows, "embedding_model", lambda: Model())
    monkeypatch.setattr(
        workflows,
        "nearest_manual_chunks",
        lambda cursor, *_a, **_k: log.append("VECTOR SEARCH") or [],
    )

    workflows.retrieve_manual("pregunta", 2, tenant=BRUNO)

    assert log[0] == "BEGIN"
    assert "set_config('app.tenant_id'" in log[1] and log[1].endswith("('2',)")
    assert log[2] == "VECTOR SEARCH"


def test_retrieval_requires_a_tenant() -> None:
    with pytest.raises(TypeError):
        workflows.retrieve_manual("pregunta", 2)  # type: ignore[call-arg]


@pytest.mark.parametrize("bad", [0, -1, "1", None, True])
def test_retrieval_rejects_an_invalid_tenant_before_any_work(
    monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    monkeypatch.setattr(workflows, "embedding_model", lambda: pytest.fail("sin modelo"))
    monkeypatch.setattr(workflows.psycopg, "connect", lambda **_: pytest.fail("sin base"))

    with pytest.raises((TypeError, ValueError)):
        workflows.retrieve_manual("pregunta", 2, tenant=Tenant("x", bad, "x"))  # type: ignore[arg-type]


def test_integrated_mode_passes_the_tenant_to_the_manual_part(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Any] = []

    def retrieve(question: str, top_k: int, document_id: str | None = None, *, tenant: Any) -> list:
        seen.append(tenant)
        return []

    monkeypatch.setattr(workflows, "retrieve_manual", retrieve)

    class Chat(_Chat):
        def chat(self, messages: list[dict[str, str]], *, max_completion_tokens: int) -> str:
            return '{"telemetry_question": null, "manual_question": "pregunta"}'

    result = workflows.run_integrated("pregunta", 2, tenant=BRUNO, client=Chat())

    assert seen == [BRUNO]
    assert "tenant=2" in result["trace"] and "rol=rag_readonly" in result["trace"]


# --- base real: RLS sobre manual_documents y manual_chunks -------------------------

_DOC = {1: "upload-0c07a0000000000000000001", 2: "upload-0c07a0000000000000000002"}
_VECTOR = "[" + ",".join(["1"] + ["0"] * 1023) + "]"


def _owner() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "ceiot_class7"),
        user=os.getenv("POSTGRES_USER", "ceiot"),
        password=os.environ["POSTGRES_PASSWORD"],
        autocommit=True,
    )


def _purge(connection: psycopg.Connection) -> None:
    ids = list(_DOC.values())
    connection.execute("DELETE FROM manual_chunks WHERE document_id = ANY(%s)", (ids,))
    connection.execute("DELETE FROM manual_documents WHERE document_id = ANY(%s)", (ids,))


@pytest.fixture
def two_tenant_documents() -> Iterator[dict[int, str]]:
    """Un documento indexado (con un chunk) por organización, como dueño de la base."""

    with _owner() as connection:
        _purge(connection)
        for organization_id, document_id in _DOC.items():
            sha = f"{organization_id:x}" * 64
            key = f"uploads/org-{organization_id}/{document_id}/v1/{sha}.pdf"
            connection.execute(
                """
                INSERT INTO manual_documents (
                    organization_id, document_id, version, title, object_key, content_type,
                    storage_status, sha256, byte_count, page_count, chunk_count,
                    embedding_model, index_status
                ) VALUES (%s, %s, 1, %s, %s, 'application/pdf', 'available', %s, 10, 1, 1,
                          'BAAI/bge-m3', 'indexed')
                """,
                (organization_id, document_id, f"Documento de prueba {organization_id}", key, sha),
            )
            connection.execute(
                """
                INSERT INTO manual_chunks (
                    organization_id, document_id, version, chunk_index, page, section,
                    content, object_key, embedding_model, embedding, content_sha256
                ) VALUES (%s, %s, 1, 0, 1, 'Sección', %s, %s, 'BAAI/bge-m3', %s::vector, %s)
                """,
                (organization_id, document_id, f"Contenido {organization_id}", key, _VECTOR, "c" * 64),
            )
        try:
            yield dict(_DOC)
        finally:
            _purge(connection)


def test_live_listing_is_filtered_by_organization(two_tenant_documents: dict[int, str]) -> None:
    ana = {item["document_id"] for item in document_catalog.list_documents(1)}
    bruno = {item["document_id"] for item in document_catalog.list_documents(2)}

    assert two_tenant_documents[1] in ana and two_tenant_documents[2] not in ana
    assert two_tenant_documents[2] in bruno and two_tenant_documents[1] not in bruno


def test_live_details_of_another_tenants_document_do_not_exist(
    two_tenant_documents: dict[int, str],
) -> None:
    assert document_catalog.document_details(two_tenant_documents[1], 1) is not None
    assert document_catalog.document_details(two_tenant_documents[1], 2) is None


def test_live_details_http_returns_404_for_another_tenants_document(
    two_tenant_documents: dict[int, str],
) -> None:
    client = TestClient(web_app.app)
    path = f"/api/documents/{two_tenant_documents[1]}"

    assert client.get(path, params={"user_id": "ana"}).status_code == 200
    assert client.get(path, params={"user_id": "bruno"}).status_code == 404


def test_live_rag_reader_without_context_sees_no_documents(
    two_tenant_documents: dict[int, str],
) -> None:
    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "ceiot_class7"),
        user="rag_readonly",
        password=os.environ["RAG_POSTGRES_PASSWORD"],
        autocommit=True,
    ) as connection:
        documents = connection.execute("SELECT count(*) FROM manual_documents").fetchone()
        chunks = connection.execute("SELECT count(*) FROM manual_chunks").fetchone()
    assert documents == (0,) and chunks == (0,)


class _FixedModel:
    def encode(self, *_args: Any, **_kwargs: Any) -> list[float]:
        return [1.0] + [0.0] * 1023


def test_live_retrieval_with_another_tenants_document_finds_nothing(
    monkeypatch: pytest.MonkeyPatch, two_tenant_documents: dict[int, str]
) -> None:
    monkeypatch.setattr(workflows, "embedding_model", lambda: _FixedModel())

    own = workflows.retrieve_manual("pregunta", 2, document_id=two_tenant_documents[1], tenant=ANA)
    foreign = workflows.retrieve_manual(
        "pregunta", 2, document_id=two_tenant_documents[1], tenant=BRUNO
    )
    open_search = workflows.retrieve_manual("pregunta", 4, tenant=BRUNO)

    assert [row["document_id"] for row in own] == [two_tenant_documents[1]]
    assert foreign == []
    assert {row["document_id"] for row in open_search} == {two_tenant_documents[2]}


def test_live_rag_for_another_tenants_document_never_calls_the_model(
    monkeypatch: pytest.MonkeyPatch, two_tenant_documents: dict[int, str]
) -> None:
    monkeypatch.setattr(workflows, "embedding_model", lambda: _FixedModel())
    chat = _Chat()

    result = workflows.run_rag(
        "pregunta", 2, document_id=two_tenant_documents[1], tenant=BRUNO, client=chat
    )

    assert chat.calls == 0
    assert result["answer"].startswith("No encontré evidencia")
    assert result["sources"] == []


def test_live_rag_trace_shows_tenant_and_role(
    monkeypatch: pytest.MonkeyPatch, two_tenant_documents: dict[int, str]
) -> None:
    monkeypatch.setattr(workflows, "embedding_model", lambda: _FixedModel())

    result = workflows.run_rag(
        "pregunta", 2, document_id=two_tenant_documents[2], tenant=BRUNO, client=_Chat()
    )

    assert "tenant=2" in result["trace"] and "rol=rag_readonly" in result["trace"]
    assert result["sources"][0]["document_id"] == two_tenant_documents[2]


def test_live_uploader_role_cannot_write_into_another_organization(
    two_tenant_documents: dict[int, str],
) -> None:
    sha = "d" * 64
    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "ceiot_class7"),
        user="rag_ingest",
        password="ceiot_rag_ingest_demo_only",  # credencial fija de la demo (compose.yaml)
    ) as connection:
        connection.execute("SELECT set_config('app.tenant_id', '1', true)")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                """
                INSERT INTO manual_documents (
                    organization_id, document_id, version, title, object_key, content_type,
                    storage_status, sha256, byte_count, page_count, chunk_count, index_status
                ) VALUES (2, 'upload-0c07a0000000000000000003', 1, 'x', 'uploads/org-2/x', 'application/pdf',
                          'pending_upload', %s, 1, 1, 0, 'pending')
                """,
                (sha,),
            )


def test_documents_tables_have_forced_rls_and_the_tenant_policy() -> None:
    with _owner() as connection:
        rows = connection.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, p.polname
            FROM pg_class c LEFT JOIN pg_policy p ON p.polrelid = c.oid
            WHERE c.relnamespace = 'public'::regnamespace
              AND c.relname IN ('manual_documents', 'manual_chunks')
            ORDER BY 1
            """
        ).fetchall()
    assert rows == [
        ("manual_chunks", True, True, "tenant_isolation"),
        ("manual_documents", True, True, "tenant_isolation"),
    ]


def test_init_scripts_declare_the_document_tenant_schema() -> None:
    rls = (ROOT / "postgres/init/07-tenant-rls.sql").read_text(encoding="utf-8")
    comments = (ROOT / "postgres/init/06-ai-open-access.sql").read_text(encoding="utf-8")

    assert "'manual_documents'" in rls and "'manual_chunks'" in rls
    assert "COMMENT ON COLUMN public.manual_documents.organization_id" in comments
    assert "COMMENT ON COLUMN public.manual_chunks.organization_id" in comments


# --- Redis: un namespace de claves por organización ---------------------------------


def test_redis_key_names_carry_the_organization_namespace() -> None:
    assert seed_services.redis_key(1, "AIR-002") == "iot:org-1:last-known:AIR-002"
    assert seed_services.redis_key(2, "PLT-001") == "iot:org-2:last-known:PLT-001"
    with pytest.raises((TypeError, ValueError)):
        seed_services.redis_key(0, "AIR-002")


def test_loader_projects_every_device_under_its_own_organization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored: dict[str, tuple[str, int]] = {}

    class FakeRedis:
        def __init__(self, **_kwargs: Any) -> None:
            return None

        def set(self, key: str, value: str, ex: int) -> None:
            stored[key] = (value, ex)

        def get(self, key: str) -> str:
            return stored[key][0]

        def ttl(self, key: str) -> int:
            return stored[key][1]

    monkeypatch.setattr(seed_services.redis, "Redis", FakeRedis)
    for name in ("REDIS_HOST", "REDIS_PORT", "REDIS_PASSWORD"):
        monkeypatch.setenv(name, "1" if name == "REDIS_PORT" else "x")
    states = {
        (1, "AIR-002"): {"device_id": "AIR-002", "readings": {}},
        (2, "PLT-001"): {"device_id": "PLT-001", "readings": {}},
    }

    seed_services.seed_redis(states)

    assert sorted(stored) == ["iot:org-1:last-known:AIR-002", "iot:org-2:last-known:PLT-001"]


def test_loader_documents_that_it_runs_as_the_admin_batch_process() -> None:
    source = (ROOT / "loader/seed_services.py").read_text(encoding="utf-8")

    assert "administrador" in source and "RLS" in source


def test_redis_tenants_are_configured_with_least_privilege_acls() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    for organization_id in (1, 2):
        assert f"tenant_{organization_id}" in compose
        assert f"ceiot_redis_tenant{organization_id}_local_only" in compose
        assert f"~iot:org-{organization_id}:*" in compose
    assert "-@all" in compose and "+get" in compose
    assert "+keys" not in compose and "+scan" not in compose


def _redis(username: str | None, password: str) -> redis.Redis:
    return redis.Redis(
        host=os.environ["REDIS_HOST"],
        port=int(os.environ["REDIS_PORT"]),
        username=username,
        password=password,
        decode_responses=True,
    )


def test_live_redis_acl_isolates_tenant_namespaces() -> None:
    admin = _redis(None, os.environ["REDIS_PASSWORD"])
    keys = {1: "iot:org-1:last-known:ACL-TEST", 2: "iot:org-2:last-known:ACL-TEST"}
    try:
        for organization_id, key in keys.items():
            admin.set(key, f"estado-{organization_id}", ex=30)
        tenant_1 = _redis("tenant_1", "ceiot_redis_tenant1_local_only")
        tenant_2 = _redis("tenant_2", "ceiot_redis_tenant2_local_only")

        assert tenant_1.get(keys[1]) == "estado-1"
        assert tenant_2.get(keys[2]) == "estado-2"
        with pytest.raises(redis.exceptions.NoPermissionError):
            tenant_1.get(keys[2])
        with pytest.raises(redis.exceptions.NoPermissionError):
            tenant_2.get(keys[1])
        with pytest.raises(redis.exceptions.NoPermissionError):
            tenant_1.set(keys[1], "pisado")
        with pytest.raises(redis.exceptions.NoPermissionError):
            tenant_1.keys("*")
    finally:
        admin.delete(*keys.values())


# --- interfaz: el usuario elegido gobierna documentos y cargas -----------------------

INDEX_HTML = (ROOT / "api" / "static" / "index.html").read_text(encoding="utf-8")


def test_ui_has_class_07_identity() -> None:
    assert "<title>Laboratorio IoT · Clase 07</title>" in INDEX_HTML
    assert "Clase 06" not in INDEX_HTML and "Clase 6" not in INDEX_HTML
    assert 'title="Laboratorio IoT Clase 07"' in (ROOT / "api/web_app.py").read_text(encoding="utf-8")


def test_ui_sends_the_selected_user_with_every_document_request() -> None:
    assert "/api/documents?user_id=" in INDEX_HTML
    assert "/api/documents/${encodeURIComponent(documentId)}?user_id=" in INDEX_HTML
    assert "organization_id" not in INDEX_HTML and "tenant_id" not in INDEX_HTML


def test_ui_announces_which_user_the_upload_belongs_to() -> None:
    assert 'id="upload-as"' in INDEX_HTML
    assert "Se cargará como:" in INDEX_HTML


def test_ui_refreshes_documents_when_the_selected_user_changes() -> None:
    start = INDEX_HTML.index("userSelect.addEventListener('change'")
    handler = INDEX_HTML[start : INDEX_HTML.index("});", start)]

    assert "loadDocuments(" in handler
    assert "hideDocumentDetails(" in handler
    assert "updateUserContext(" in handler


def test_ui_links_to_the_schema_the_model_receives() -> None:
    assert 'id="schema-link"' in INDEX_HTML
    assert "Ver esquema que recibe el modelo" in INDEX_HTML
    assert "/api/sql-schema?user_id=" in INDEX_HTML


def test_ui_shows_the_querying_user_for_every_mode() -> None:
    assert "Consultando como:" in INDEX_HTML
    assert "innerHTML" not in INDEX_HTML
