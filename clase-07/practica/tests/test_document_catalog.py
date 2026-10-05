from __future__ import annotations

import os
from typing import Any

import psycopg  # type: ignore[import-not-found]
import pytest  # type: ignore[import-not-found]

from shared import document_catalog  # type: ignore[import-not-found]
from shared.rag_connection import (  # type: ignore[import-not-found]
    rag_connection_settings,
    validate_document_id,
)

DOCUMENT_ID = "upload-0123456789abcdef01234567"
DOCUMENT_ROW = {
    "document_id": DOCUMENT_ID,
    "version": 1,
    "title": "Informe de ventilación",
    "object_key": f"uploads/{DOCUMENT_ID}/v1/report.pdf",
    "pages": 2,
    "chunk_count": 2,
    "model": "BAAI/bge-m3",
    "sha": "a" * 64,
    "bytes": 4096,
    "status": "indexed",
}


class _Cursor:
    def __init__(
        self,
        *,
        fetchone_rows: list[dict[str, Any] | None] | None = None,
        fetchall_rows: list[list[dict[str, Any]]] | None = None,
    ) -> None:
        self.fetchone_rows = list(fetchone_rows or [])
        self.fetchall_rows = list(fetchall_rows or [])
        self.executions: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.executions.append((" ".join(sql.split()), params))

    def fetchone(self) -> dict[str, Any] | None:
        return self.fetchone_rows.pop(0)

    def fetchall(self) -> list[dict[str, Any]]:
        return self.fetchall_rows.pop(0)


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> _Connection:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        return None

    def cursor(self) -> _Cursor:
        return self._cursor


def _install_connection(
    monkeypatch: pytest.MonkeyPatch, cursor: _Cursor
) -> list[dict[str, Any]]:
    settings: list[dict[str, Any]] = []

    def connect(**kwargs: Any) -> _Connection:
        settings.append(kwargs)
        return _Connection(cursor)

    monkeypatch.setattr(document_catalog.psycopg, "connect", connect)
    monkeypatch.setenv("RAG_POSTGRES_PASSWORD", "catalog-test-password")
    monkeypatch.setenv("RAG_POSTGRES_USER", "rag_readonly")
    return settings


def test_read_connection_is_pinned_to_rag_readonly_without_owner_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAG_POSTGRES_USER", "rag_readonly")
    monkeypatch.setenv("RAG_POSTGRES_PASSWORD", "role-specific-secret")
    monkeypatch.setenv("POSTGRES_USER", "owner-must-not-be-used")
    monkeypatch.setenv("POSTGRES_PASSWORD", "owner-secret-must-not-be-used")

    settings = rag_connection_settings()

    assert settings["user"] == "rag_readonly"
    assert settings["password"] == os.environ["RAG_POSTGRES_PASSWORD"]
    assert "owner-must-not-be-used" not in settings.values()
    assert "owner-secret-must-not-be-used" not in settings.values()

    monkeypatch.setenv("RAG_POSTGRES_USER", "ceiot")
    with pytest.raises(RuntimeError, match="rag_readonly"):
        rag_connection_settings()


@pytest.mark.parametrize(
    "document_id",
    ["env-x-manual", DOCUMENT_ID],
)
def test_document_id_accepts_only_seed_or_sha_derived_upload(document_id: str) -> None:
    assert validate_document_id(document_id) == document_id


@pytest.mark.parametrize(
    "document_id",
    ["", "upload-xyz", "upload-" + "a" * 25, "other-manual", "x' OR 1=1 --"],
)
def test_document_id_rejects_unbounded_or_noncanonical_values(document_id: str) -> None:
    with pytest.raises(ValueError, match="formato válido"):
        validate_document_id(document_id)


def test_list_documents_returns_exact_bounded_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _Cursor(fetchall_rows=[[DOCUMENT_ROW]])
    observed_settings = _install_connection(monkeypatch, cursor)

    result = document_catalog.list_documents()

    assert result == [
        {
            "document_id": DOCUMENT_ID,
            "title": "Informe de ventilación",
            "object_key": DOCUMENT_ROW["object_key"],
            "pages": 2,
            "chunk_count": 2,
            "model": "BAAI/bge-m3",
            "sha": "a" * 64,
            "bytes": 4096,
            "status": "indexed",
        }
    ]
    sql, params = cursor.executions[0]
    assert "FROM public.manual_documents" in sql
    assert "storage_status = %s" in sql and "index_status = %s" in sql
    assert "left(title, 200)" in sql and "left(object_key, 512)" in sql
    assert "LIMIT %s" in sql
    assert params == ("available", "indexed", 120, 100)
    assert observed_settings[0]["user"] == "rag_readonly"


def test_document_details_returns_ordered_bounded_chunks_and_six_float_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vector = "[" + ",".join(str(index / 1000) for index in range(1024)) + "]"
    chunk_rows = [
        {
            "chunk_index": index,
            "page": index + 1,
            "section": f"Página {index + 1}",
            "content": f"Contenido {index + 1}",
            "content_sha256": str(index) * 64,
            "vector_dims": 1024,
            "embedding_text": vector,
        }
        for index in range(2)
    ]
    cursor = _Cursor(fetchone_rows=[DOCUMENT_ROW], fetchall_rows=[chunk_rows])
    _install_connection(monkeypatch, cursor)

    result = document_catalog.document_details(DOCUMENT_ID)

    assert result is not None
    assert set(result) == {
        "document_id",
        "title",
        "object_key",
        "pages",
        "chunk_count",
        "model",
        "sha",
        "bytes",
        "status",
        "chunks",
    }
    assert [chunk["chunk_index"] for chunk in result["chunks"]] == [0, 1]
    assert result["chunks"][0] == {
        "chunk_index": 0,
        "page": 1,
        "section": "Página 1",
        "content": "Contenido 1",
        "content_sha256": "0" * 64,
        "vector_dims": 1024,
        "embedding_preview": [0.0, 0.001, 0.002, 0.003, 0.004, 0.005],
    }
    assert all("embedding_text" not in chunk for chunk in result["chunks"])
    document_sql, document_params = cursor.executions[0]
    chunks_sql, chunks_params = cursor.executions[1]
    assert document_params == ("available", "indexed", DOCUMENT_ID)
    assert "document_id = %s" in document_sql
    assert "ORDER BY chunk.chunk_index LIMIT %s" in chunks_sql
    assert "left(chunk.content, 1200)" in chunks_sql
    assert "chunk.embedding::text" in chunks_sql
    assert "vector_dims(chunk.embedding) = 1024" in chunks_sql
    assert chunks_params == (DOCUMENT_ID, 1, "available", "indexed", 120)


def test_document_details_returns_none_for_unknown_valid_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _Cursor(fetchone_rows=[None])
    _install_connection(monkeypatch, cursor)

    assert document_catalog.document_details(DOCUMENT_ID) is None
    assert len(cursor.executions) == 1


def test_catalog_errors_are_sanitized_and_do_not_expose_database_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAG_POSTGRES_PASSWORD", "not-returned")
    monkeypatch.setenv("RAG_POSTGRES_USER", "rag_readonly")

    def fail_connect(**_kwargs: Any) -> Any:
        raise psycopg.OperationalError("host=private password=supersecret")

    monkeypatch.setattr(document_catalog.psycopg, "connect", fail_connect)

    with pytest.raises(document_catalog.CatalogUnavailable) as captured:
        document_catalog.list_documents()

    assert str(captured.value) == (
        "El catálogo de documentos no está disponible temporalmente."
    )
    assert "private" not in str(captured.value)
    assert "supersecret" not in str(captured.value)
