"""Bounded read-only access to indexed PDF catalog metadata and chunks."""

from __future__ import annotations

import json
import math
from typing import Any

import psycopg  # type: ignore[import-not-found]

from shared.document_limits import MAX_CHUNK_CHARS  # type: ignore[import-not-found]
from shared.embeddings import EXPECTED_DIMENSION  # type: ignore[import-not-found]
from shared.rag_connection import (  # type: ignore[import-not-found]
    rag_connection_settings,
    validate_document_id,
)

MAX_DOCUMENTS = 100
MAX_DOCUMENT_CHUNKS = 120
# vector(1024) rendered as text (8-decimal floats, comma separated, with
# brackets) can reach roughly 1024 * 12 characters; bound generously above
# that so a legitimate embedding is never rejected as oversized.
MAX_EMBEDDING_TEXT_CHARS = 20_000


class CatalogUnavailable(RuntimeError):
    """Sanitized catalog infrastructure failure safe for an API boundary."""

    def __init__(self) -> None:
        super().__init__("El catálogo de documentos no está disponible temporalmente.")



def _document_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": row["document_id"],
        "title": row["title"],
        "object_key": row["object_key"],
        "pages": row["pages"],
        "chunk_count": row["chunk_count"],
        "model": row["model"],
        "sha": row["sha"],
        "bytes": row["bytes"],
        "status": row["status"],
    }


def _embedding_preview(raw_vector: Any, vector_dims: Any) -> list[float]:
    """Parse pgvector text without evaluation and expose only six finite numbers."""

    if (
        vector_dims != EXPECTED_DIMENSION
        or not isinstance(raw_vector, str)
        or len(raw_vector) > MAX_EMBEDDING_TEXT_CHARS
    ):
        return []
    try:
        parsed = json.loads(raw_vector)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list) or len(parsed) != EXPECTED_DIMENSION:
        return []

    preview: list[float] = []
    for value in parsed[:6]:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return []
        converted = float(value)
        if not math.isfinite(converted):
            return []
        preview.append(converted)
    return preview


def list_documents() -> list[dict[str, Any]]:
    """List at most 100 documents whose object and vector index are available."""

    try:
        with (
            psycopg.connect(**rag_connection_settings()) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                SELECT document_id,
                       left(title, 200) AS title,
                       left(object_key, 512) AS object_key,
                       page_count AS pages,
                       chunk_count,
                       left(embedding_model, 200) AS model,
                       sha256 AS sha,
                       byte_count AS bytes,
                       index_status AS status
                FROM public.manual_documents
                WHERE storage_status = %s
                  AND index_status = %s
                  AND chunk_count >= 1
                ORDER BY title, document_id
                LIMIT %s
                """,
                # MAX_DOCUMENT_CHUNKS acota sólo la vista de detalle: un PDF largo
                # (cientos de fragmentos) también debe aparecer en el listado.
                ("available", "indexed", MAX_DOCUMENTS),
            )
            return [_document_summary(dict(row)) for row in cursor.fetchall()]
    except (psycopg.Error, TimeoutError, KeyError, RuntimeError, ValueError) as error:
        raise CatalogUnavailable() from error


def document_details(document_id: str) -> dict[str, Any] | None:
    """Return one indexed document and at most 120 ordered, bounded chunks."""

    selected_id = validate_document_id(document_id)
    try:
        with (
            psycopg.connect(**rag_connection_settings()) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                SELECT document_id, version,
                       left(title, 200) AS title,
                       left(object_key, 512) AS object_key,
                       page_count AS pages,
                       chunk_count,
                       left(embedding_model, 200) AS model,
                       sha256 AS sha,
                       byte_count AS bytes,
                       index_status AS status
                FROM public.manual_documents
                WHERE storage_status = %s
                  AND index_status = %s
                  AND document_id = %s
                ORDER BY version DESC
                LIMIT 1
                """,
                ("available", "indexed", selected_id),
            )
            document_row = cursor.fetchone()
            if document_row is None:
                return None
            document = dict(document_row)

            cursor.execute(
                f"""
                SELECT chunk.chunk_index,
                       chunk.page,
                       left(chunk.section, 200) AS section,
                       left(chunk.content, {MAX_CHUNK_CHARS}) AS content,
                       chunk.content_sha256,
                       vector_dims(chunk.embedding) AS vector_dims,
                       chunk.embedding::text AS embedding_text
                FROM public.manual_chunks AS chunk
                JOIN public.manual_documents AS document
                  ON document.document_id = chunk.document_id
                 AND document.version = chunk.version
                 AND document.object_key = chunk.object_key
                WHERE chunk.document_id = %s
                  AND chunk.version = %s
                  AND document.storage_status = %s
                  AND document.index_status = %s
                  AND vector_dims(chunk.embedding) = 1024
                ORDER BY chunk.chunk_index
                LIMIT %s
                """,
                (
                    selected_id,
                    document["version"],
                    "available",
                    "indexed",
                    MAX_DOCUMENT_CHUNKS,
                ),
            )
            chunks = []
            for row in cursor.fetchall():
                chunk = dict(row)
                chunks.append(
                    {
                        "chunk_index": chunk["chunk_index"],
                        "page": chunk["page"],
                        "section": chunk["section"],
                        "content": chunk["content"],
                        "content_sha256": chunk["content_sha256"],
                        "vector_dims": chunk["vector_dims"],
                        "embedding_preview": _embedding_preview(
                            chunk["embedding_text"], chunk["vector_dims"]
                        ),
                    }
                )
            result = _document_summary(document)
            result["chunks"] = chunks
            return result
    except (psycopg.Error, TimeoutError, KeyError, RuntimeError, ValueError) as error:
        raise CatalogUnavailable() from error
