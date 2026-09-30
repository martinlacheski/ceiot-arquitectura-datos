from __future__ import annotations

import hashlib
import io
import os
from dataclasses import replace
from typing import Any

import pytest  # type: ignore[import-not-found]

import loader.pdf_storage as pdf_storage  # type: ignore[import-not-found]
from loader.pdf_document import (  # type: ignore[import-not-found]
    PDFRejected,
    PageChunk,
    ParsedDocument,
)
from shared.embeddings import EXPECTED_DIMENSION, MODEL_NAME  # type: ignore[import-not-found]


PDF_BYTES = b"%PDF synthetic storage test"


def _document(pdf_bytes: bytes = PDF_BYTES) -> ParsedDocument:
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    document_id = f"upload-{digest[:24]}"
    object_key = f"uploads/{document_id}/v1/{digest}.pdf"
    chunks = tuple(
        PageChunk(
            document_id=document_id,
            version=1,
            page=index + 1,
            section=f"Pagina {index + 1}",
            chunk_index=index,
            content=f"Contenido significativo del fragmento {index + 1}.",
            object_key=object_key,
        )
        for index in range(2)
    )
    return ParsedDocument(
        document_id=document_id,
        version=1,
        title="Informe seguro",
        sha256=digest,
        byte_count=len(pdf_bytes),
        page_count=2,
        extracted_char_count=sum(len(chunk.content) for chunk in chunks),
        object_key=object_key,
        chunks=chunks,
    )


class _Model:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.inputs: list[str] = []
        self.normalize_embeddings: bool | None = None

    def encode(self, inputs: list[str], normalize_embeddings: bool) -> list[list[float]]:
        self.events.append("embed")
        self.inputs = inputs
        self.normalize_embeddings = normalize_embeddings
        return [
            [float(chunk_index) + dimension / 1000 for dimension in range(EXPECTED_DIMENSION)]
            for chunk_index in range(len(inputs))
        ]


class _Body(io.BytesIO):
    closed_by_loader = False

    def close(self) -> None:
        self.closed_by_loader = True
        super().close()


class _S3:
    def __init__(self, events: list[str], metadata_override: dict[str, str] | None = None) -> None:
        self.events = events
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], dict[str, Any]] = {}
        self.metadata_override = metadata_override
        self.last_body: _Body | None = None

    def list_buckets(self) -> dict[str, Any]:
        return {"Buckets": [{"Name": name} for name in sorted(self.buckets)]}

    def create_bucket(self, Bucket: str) -> None:
        self.events.append("s3_create_bucket")
        self.buckets.add(Bucket)

    def put_object(self, **kwargs: Any) -> None:
        self.events.append("s3_put")
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = dict(kwargs)

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        self.events.append("s3_head")
        stored = self.objects[(Bucket, Key)]
        return {
            "ContentType": stored["ContentType"],
            "ContentLength": len(stored["Body"]),
            "Metadata": self.metadata_override or stored["Metadata"],
        }

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        self.events.append("s3_get")
        self.last_body = _Body(self.objects[(Bucket, Key)]["Body"])
        return {"Body": self.last_body}


class _Cursor:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection
        self.rowcount = 1
        self._fetchone: tuple[str, str] | None = None

    def __enter__(self) -> _Cursor:
        self.connection._snapshot = set(self.connection.chunk_keys)
        self.connection._title_snapshot = dict(self.connection.document_titles)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        normalized = " ".join(sql.split())
        self.connection.executions.append((normalized, params))
        if self.connection.fail_on and self.connection.fail_on in normalized:
            raise RuntimeError("SENTINEL database credential and internal detail")
        if normalized.startswith("INSERT INTO manual_documents"):
            key = (params[0], params[1])
            if self.connection.collision:
                self._fetchone = None
            else:
                title = self.connection.document_titles.setdefault(key, params[2])
                self._fetchone = (params[5], title)
        elif normalized.startswith("DELETE FROM manual_chunks"):
            document_id, version = params
            self.connection.chunk_keys = {
                key for key in self.connection.chunk_keys if key[:2] != (document_id, version)
            }
        elif normalized.startswith("INSERT INTO manual_chunks"):
            self.connection.chunk_keys.add((params[0], params[1], params[2]))
        elif normalized.startswith("UPDATE manual_documents"):
            self.rowcount = 1

    def fetchone(self) -> tuple[str, str] | None:
        return self._fetchone


class _Connection:
    def __init__(self, events: list[str], fail_on: str | None = None) -> None:
        self.events = events
        self.fail_on = fail_on
        self.collision = False
        self.executions: list[tuple[str, tuple[Any, ...]]] = []
        self.chunk_keys: set[tuple[str, int, int]] = set()
        self.document_titles: dict[tuple[str, int], str] = {}
        self._snapshot: set[tuple[str, int, int]] = set()
        self._title_snapshot: dict[tuple[str, int], str] = {}
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self) -> _Cursor:
        self.events.append("db_cursor")
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1
        self.chunk_keys = set(self._snapshot)
        self.document_titles = dict(self._title_snapshot)

    def close(self) -> None:
        self.closed += 1


def _install_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    document: ParsedDocument,
    model: _Model,
    s3: _S3,
    connection: _Connection,
) -> None:
    monkeypatch.setattr(pdf_storage, "parse_document", lambda *_args: document)
    monkeypatch.setattr(pdf_storage, "embedding_model", lambda: model)
    monkeypatch.setattr(pdf_storage, "_s3_client", lambda: s3)

    def connect() -> _Connection:
        connection.events.append("db_connect")
        return connection

    monkeypatch.setattr(pdf_storage, "_postgres_connection", connect)
    monkeypatch.setenv("MANUAL_BUCKET", "manuales")


def test_ingest_returns_safe_summary_and_orders_verified_s3_before_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    document = _document()
    model = _Model(events)
    s3 = _S3(events)
    connection = _Connection(events)
    _install_dependencies(monkeypatch, document, model, s3, connection)

    result = pdf_storage.ingest_document(PDF_BYTES, "Informe", "application/pdf")

    assert events == [
        "embed",
        "s3_create_bucket",
        "s3_put",
        "s3_head",
        "s3_get",
        "db_connect",
        "db_cursor",
    ]
    assert model.normalize_embeddings is True
    assert all(not text.startswith("passage:") for text in model.inputs)
    assert s3.last_body is not None and s3.last_body.closed_by_loader
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert result == {
        "document_id": document.document_id,
        "version": 1,
        "title": document.title,
        "object_key": document.object_key,
        "sha256": document.sha256,
        "byte_count": len(PDF_BYTES),
        "page_count": 2,
        "extracted_char_count": document.extracted_char_count,
        "chunk_count": 2,
        "embedding_model": MODEL_NAME,
        "dimension": 1024,
        "index_status": "indexed",
        "embedding_preview": [dimension / 1000 for dimension in range(6)],
        "trace": [
            "pdf_validated",
            "chunks_embedded",
            "s3_stored",
            "s3_verified",
            "postgres_indexed",
        ],
    }
    assert "content" not in result and len(result["embedding_preview"]) == 6


def test_database_failure_rolls_back_but_keeps_retryable_s3_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    document = _document()
    model = _Model(events)
    s3 = _S3(events)
    connection = _Connection(events, fail_on="INSERT INTO manual_chunks")
    _install_dependencies(monkeypatch, document, model, s3, connection)

    with pytest.raises(pdf_storage.UploadUnavailable) as captured:
        pdf_storage.ingest_document(PDF_BYTES, "Informe", "application/pdf")

    assert str(captured.value) == "La carga no está disponible temporalmente."
    assert "SENTINEL" not in str(captured.value)
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.chunk_keys == set()
    assert ("manuales", document.object_key) in s3.objects
    assert connection.closed == 1


def test_finalization_failure_restores_original_chunks_and_keeps_s3_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    document = _document()
    model = _Model(events)
    s3 = _S3(events)
    connection = _Connection(events, fail_on="UPDATE manual_documents")
    original_keys = {
        (document.document_id, document.version, 7),
        (document.document_id, document.version, 9),
        ("upload-other-document", 3, 4),
    }
    connection.chunk_keys = set(original_keys)
    _install_dependencies(monkeypatch, document, model, s3, connection)

    with pytest.raises(pdf_storage.UploadUnavailable):
        pdf_storage.ingest_document(PDF_BYTES, "Informe", "application/pdf")

    inserted_keys = {
        (params[0], params[1], params[2])
        for sql, params in connection.executions
        if sql.startswith("INSERT INTO manual_chunks")
    }
    assert inserted_keys == {
        (document.document_id, document.version, chunk.chunk_index)
        for chunk in document.chunks
    }
    assert connection.chunk_keys == original_keys
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert ("manuales", document.object_key) in s3.objects


def test_retry_replaces_exact_version_without_duplicate_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    document = _document()
    model = _Model(events)
    s3 = _S3(events)
    connection = _Connection(events)
    _install_dependencies(monkeypatch, document, model, s3, connection)

    first = pdf_storage.ingest_document(PDF_BYTES, "Informe", "application/pdf")
    second = pdf_storage.ingest_document(PDF_BYTES, "Informe", "application/pdf")

    assert first["document_id"] == second["document_id"]
    assert connection.commits == 2
    assert connection.chunk_keys == {
        (document.document_id, document.version, chunk.chunk_index)
        for chunk in document.chunks
    }
    deletes = [sql for sql, _params in connection.executions if sql.startswith("DELETE")]
    assert len(deletes) == 2


def test_reupload_preserves_original_title_and_returns_stored_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    document = _document()
    model = _Model(events)
    s3 = _S3(events)
    connection = _Connection(events)
    _install_dependencies(monkeypatch, document, model, s3, connection)

    first = pdf_storage.ingest_document(PDF_BYTES, "Informe seguro", "application/pdf")
    changed_title = replace(document, title="Nuevo título no persistido")
    _install_dependencies(monkeypatch, changed_title, model, s3, connection)
    repeated = pdf_storage.ingest_document(PDF_BYTES, "Nuevo título", "application/pdf")

    assert first["title"] == repeated["title"] == document.title
    assert first["document_id"] == repeated["document_id"]
    assert connection.document_titles[(document.document_id, 1)] == document.title


def test_vectors_are_parameterized_and_connection_uses_only_ingest_role_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    postgres_connection = pdf_storage._postgres_connection
    events: list[str] = []
    document = _document()
    model = _Model(events)
    s3 = _S3(events)
    connection = _Connection(events)
    _install_dependencies(monkeypatch, document, model, s3, connection)

    pdf_storage.ingest_document(PDF_BYTES, "Informe", "application/pdf")

    chunk_inserts = [
        (sql, params)
        for sql, params in connection.executions
        if sql.startswith("INSERT INTO manual_chunks")
    ]
    assert len(chunk_inserts) == len(document.chunks)
    assert all("%s::vector" in sql for sql, _params in chunk_inserts)
    assert all(
        params[8].startswith("[") and params[8].endswith("]")
        for _sql, params in chunk_inserts
    )
    assert all(len(params[9]) == 64 for _sql, params in chunk_inserts)

    observed: dict[str, Any] = {}
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "ceiot_class6")
    monkeypatch.setenv("POSTGRES_USER", "owner-must-not-be-used")
    monkeypatch.setenv("POSTGRES_PASSWORD", "owner-secret-must-not-be-used")
    monkeypatch.setenv("RAG_INGEST_POSTGRES_PASSWORD", "role-specific-test-value")
    monkeypatch.setattr(
        pdf_storage.psycopg,
        "connect",
        lambda **kwargs: observed.update(kwargs) or object(),
    )

    postgres_connection()

    assert observed["user"] == "rag_ingest"
    assert observed["password"] == os.environ["RAG_INGEST_POSTGRES_PASSWORD"]
    assert "owner-must-not-be-used" not in observed.values()
    assert "owner-secret-must-not-be-used" not in observed.values()


def test_s3_metadata_mismatch_stops_before_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    document = _document()
    model = _Model(events)
    s3 = _S3(events, metadata_override={"sha256": "0" * 64})
    connection = _Connection(events)
    _install_dependencies(monkeypatch, document, model, s3, connection)

    with pytest.raises(pdf_storage.UploadUnavailable):
        pdf_storage.ingest_document(PDF_BYTES, "Informe", "application/pdf")

    assert "db_connect" not in events
    assert connection.executions == []


def test_validated_embeddings_accepts_float32_numpy_and_rejects_invalid_arrays() -> None:
    import numpy as np  # type: ignore[import-not-found]

    raw = np.arange(2 * EXPECTED_DIMENSION, dtype=np.float32).reshape(
        2, EXPECTED_DIMENSION
    )

    validated = pdf_storage._validated_embeddings(raw, chunk_count=2)

    assert validated == raw.astype(float).tolist()
    assert all(type(value) is float for embedding in validated for value in embedding)

    with pytest.raises(ValueError, match="Unexpected embedding count"):
        pdf_storage._validated_embeddings(raw[:1], chunk_count=2)
    with pytest.raises(ValueError, match="Unexpected embedding dimension"):
        pdf_storage._validated_embeddings(raw[:, :-1], chunk_count=2)

    nonfinite = raw.copy()
    nonfinite[1, 17] = np.inf
    with pytest.raises(ValueError, match="Embedding contains a non-finite value"):
        pdf_storage._validated_embeddings(nonfinite, chunk_count=2)


def test_embedding_shape_and_document_id_collision_fail_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    document = _document()
    model = _Model(events)
    s3 = _S3(events)
    connection = _Connection(events)
    _install_dependencies(monkeypatch, document, model, s3, connection)
    model.encode = lambda *_args, **_kwargs: [[0.0] * (EXPECTED_DIMENSION - 1) for _ in document.chunks]  # type: ignore[method-assign]

    with pytest.raises(pdf_storage.UploadUnavailable):
        pdf_storage.ingest_document(PDF_BYTES, "Informe", "application/pdf")
    assert s3.objects == {}

    model = _Model(events)
    connection.collision = True
    _install_dependencies(monkeypatch, document, model, s3, connection)
    with pytest.raises(pdf_storage.UploadUnavailable):
        pdf_storage.ingest_document(PDF_BYTES, "Informe", "application/pdf")
    assert connection.rollbacks == 1
    assert connection.commits == 0


def test_pdf_rejection_remains_distinct_and_precedes_all_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject(*_args: Any) -> ParsedDocument:
        raise PDFRejected("PDF rechazado de forma segura.")

    monkeypatch.setattr(pdf_storage, "parse_document", reject)
    monkeypatch.setattr(
        pdf_storage,
        "embedding_model",
        lambda: pytest.fail("embedding must not run"),
    )
    monkeypatch.setattr(pdf_storage, "_s3_client", lambda: pytest.fail("S3 must not run"))
    monkeypatch.setattr(
        pdf_storage,
        "_postgres_connection",
        lambda: pytest.fail("database must not run"),
    )

    with pytest.raises(PDFRejected, match="PDF rechazado de forma segura"):
        pdf_storage.ingest_document(b"invalid", "Informe", "application/pdf")
