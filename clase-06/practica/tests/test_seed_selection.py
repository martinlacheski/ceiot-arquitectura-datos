from __future__ import annotations

import os
import sys
from typing import Any

import pytest  # type: ignore[import-not-found]

from loader import query_vectors  # type: ignore[import-not-found]
from loader.ingest_vectors import (  # type: ignore[import-not-found]
    SEED_DOCUMENT_ID,
    postgres_connection,
    read_available_document,
)


class FakeCatalogCursor:
    def __init__(self, documents: list[tuple[str, int, str, str]]) -> None:
        self.documents = documents
        self.sql = ""
        self.params: tuple[Any, ...] = ()

    def __enter__(self) -> FakeCatalogCursor:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.sql = " ".join(sql.split())
        self.params = params

    def fetchone(self) -> tuple[str, int, str] | None:
        selected_id = self.params[0]
        candidates = [
            (document_id, version, object_key)
            for document_id, version, object_key, storage_status in self.documents
            if document_id == selected_id and storage_status == "available"
        ]
        return max(candidates, key=lambda row: row[1], default=None)


class FakeCatalogConnection:
    def __init__(self, documents: list[tuple[str, int, str, str]]) -> None:
        self.catalog_cursor = FakeCatalogCursor(documents)

    def cursor(self) -> FakeCatalogCursor:
        return self.catalog_cursor


def test_seed_selection_parameterizes_canonical_id_and_keeps_newest_version() -> None:
    connection = FakeCatalogConnection(
        [
            (SEED_DOCUMENT_ID, 1, "manuales/env-x/v1/manual_ENV_X_v1.pdf", "available"),
            (SEED_DOCUMENT_ID, 2, "manuales/env-x/v2/manual_ENV_X_v2.pdf", "available"),
            ("upload-0123456789abcdef01234567", 99, "uploads/new.pdf", "available"),
        ]
    )

    selected = read_available_document(connection)  # type: ignore[arg-type]

    assert selected == (SEED_DOCUMENT_ID, 2, "manuales/env-x/v2/manual_ENV_X_v2.pdf")
    assert "WHERE document_id = %s" in connection.catalog_cursor.sql
    assert "storage_status = 'available'" in connection.catalog_cursor.sql
    assert "ORDER BY version DESC" in connection.catalog_cursor.sql
    assert connection.catalog_cursor.params == (SEED_DOCUMENT_ID,)


def test_available_upload_is_not_used_when_canonical_seed_is_unavailable() -> None:
    connection = FakeCatalogConnection(
        [
            (SEED_DOCUMENT_ID, 1, "manuales/env-x/v1/manual_ENV_X.pdf", "pending_upload"),
            ("upload-0123456789abcdef01234567", 2, "uploads/new.pdf", "available"),
        ]
    )

    with pytest.raises(RuntimeError, match="env-x-manual.*no está disponible"):
        read_available_document(connection)  # type: ignore[arg-type]

    assert "WHERE document_id = %s" in connection.catalog_cursor.sql
    assert connection.catalog_cursor.params == (SEED_DOCUMENT_ID,)


def test_cli_rejects_top_k_five_before_model_or_external_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["query_vectors.py", "--top-k", "5"])
    monkeypatch.setattr(
        query_vectors,
        "embedding_model",
        lambda: pytest.fail("model must not load"),
    )
    monkeypatch.setattr(
        query_vectors,
        "postgres_connection",
        lambda: pytest.fail("database must not connect"),
    )

    with pytest.raises(SystemExit, match=r"--top-k debe estar entre 1 y 4"):
        query_vectors.main()


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_SEED_CATALOG_CHECK") != "1",
    reason="set RUN_LIVE_SEED_CATALOG_CHECK=1 for the read-only current-volume check",
)
def test_live_catalog_selects_canonical_seed_identity_read_only() -> None:
    with postgres_connection() as connection:
        document_id, version, object_key = read_available_document(connection)

    assert document_id == SEED_DOCUMENT_ID
    assert version >= 1
    assert object_key
