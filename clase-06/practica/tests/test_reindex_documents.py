from __future__ import annotations

import hashlib
import io
from typing import Any

import pytest  # type: ignore[import-not-found]
from reportlab.pdfgen import canvas  # type: ignore[import-not-found]

import loader.reindex_documents as reindex_documents  # type: ignore[import-not-found]
from loader import pdf_storage  # type: ignore[import-not-found]
from loader.pdf_document import PDFRejected  # type: ignore[import-not-found]


def _pdf_bytes(text: str) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output)
    document.drawString(50, 790, text)
    document.showPage()
    document.save()
    return output.getvalue()


PDF_BYTES = _pdf_bytes("Contenido de reindexación suficiente para extraer texto.")


def _document_id(pdf_bytes: bytes) -> str:
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    return f"upload-{digest[:24]}"


def _object_key(pdf_bytes: bytes) -> str:
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    return f"uploads/{_document_id(pdf_bytes)}/v1/{digest}.pdf"


class _Cursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows
        self.executions: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.executions.append((" ".join(sql.split()), params))

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor
        self.closed = 0

    def cursor(self) -> _Cursor:
        return self._cursor

    def commit(self) -> None:
        pass

    def close(self) -> None:
        self.closed += 1


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.closed = False

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        self.closed = True


class _S3:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.requested_keys: list[str] = []

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        self.requested_keys.append(Key)
        return {"Body": _Body(self.objects[Key])}


def test_pending_uploaded_documents_filters_available_not_indexed_uploads() -> None:
    rows = [
        ("upload-aaaaaaaaaaaaaaaaaaaaaaaa", 1, "Informe", "uploads/upload-aaa/v1/x.pdf"),
    ]
    cursor = _Cursor(rows)
    connection = _Connection(cursor)

    pending = reindex_documents.pending_uploaded_documents(connection)

    assert pending == [
        reindex_documents.PendingDocument(
            document_id="upload-aaaaaaaaaaaaaaaaaaaaaaaa",
            version=1,
            title="Informe",
            object_key="uploads/upload-aaa/v1/x.pdf",
        )
    ]
    sql, params = cursor.executions[0]
    assert "storage_status = 'available'" in sql
    assert "index_status <> 'indexed'" in sql
    assert "document_id LIKE %s" in sql
    assert params == ("upload-%",)


def test_reindex_document_reuses_parse_embed_and_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    document_id = _document_id(PDF_BYTES)
    object_key = _object_key(PDF_BYTES)
    pending = reindex_documents.PendingDocument(
        document_id=document_id, version=1, title="Informe", object_key=object_key
    )
    s3 = _S3({object_key: PDF_BYTES})

    def fake_embed(document: Any) -> list[list[float]]:
        events.append("embed")
        return [[0.0] * 1024 for _ in document.chunks]

    def fake_persist(connection: Any, document: Any, embeddings: Any) -> str:
        events.append("persist")
        return document.title

    monkeypatch.setattr(pdf_storage, "_embed_document", fake_embed)
    monkeypatch.setattr(pdf_storage, "_persist_document", fake_persist)

    result = reindex_documents.reindex_document(object(), s3, "manuales", pending)

    assert events == ["embed", "persist"]
    assert s3.requested_keys == [object_key]
    assert result["document_id"] == document_id
    assert result["version"] == 1
    assert result["chunk_count"] >= 1


def test_reindex_document_rejects_identity_mismatch_without_persisting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other_bytes = _pdf_bytes("Contenido completamente distinto para probar el rechazo.")
    pending = reindex_documents.PendingDocument(
        document_id=_document_id(PDF_BYTES),
        version=1,
        title="Informe",
        object_key=_object_key(PDF_BYTES),
    )
    # The object stored under this key no longer matches the registered identity.
    s3 = _S3({pending.object_key: other_bytes})
    monkeypatch.setattr(
        pdf_storage,
        "_embed_document",
        lambda *_a: pytest.fail("must not embed a mismatched document"),
    )
    monkeypatch.setattr(
        pdf_storage,
        "_persist_document",
        lambda *_a: pytest.fail("must not persist a mismatched document"),
    )

    with pytest.raises(ValueError, match="no coincide"):
        reindex_documents.reindex_document(object(), s3, "manuales", pending)


def test_main_reports_failures_without_raising_and_closes_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ok_pending = reindex_documents.PendingDocument(
        document_id="upload-0000000000000000000000ok",
        version=1,
        title="OK",
        object_key="uploads/ok/v1/ok.pdf",
    )
    broken_pending = reindex_documents.PendingDocument(
        document_id="upload-0000000000000000000000bad",
        version=1,
        title="Roto",
        object_key="uploads/bad/v1/bad.pdf",
    )
    connection = _Connection(_Cursor([]))
    monkeypatch.setattr(pdf_storage, "_postgres_connection", lambda: connection)
    monkeypatch.setattr(pdf_storage, "_s3_client", lambda: object())
    monkeypatch.setenv("MANUAL_BUCKET", "manuales")
    monkeypatch.setattr(
        reindex_documents,
        "pending_uploaded_documents",
        lambda _connection: [ok_pending, broken_pending],
    )

    def fake_reindex(_connection: Any, _client: Any, _bucket: str, pending: Any) -> dict[str, Any]:
        if pending is broken_pending:
            raise PDFRejected("el PDF quedó corrupto en almacenamiento")
        return {"document_id": pending.document_id, "version": pending.version, "chunk_count": 3}

    monkeypatch.setattr(reindex_documents, "reindex_document", fake_reindex)

    with pytest.raises(SystemExit):
        reindex_documents.main()

    assert connection.closed == 1
