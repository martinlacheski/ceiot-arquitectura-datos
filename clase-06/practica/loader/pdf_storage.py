"""Persist validated PDF documents in local S3 and PostgreSQL/pgvector."""

from __future__ import annotations

import hashlib
import math
import numbers
import os
from collections.abc import Sequence
from typing import Any

import boto3  # type: ignore[import-not-found]
from botocore import UNSIGNED  # type: ignore[import-not-found]
from botocore.config import Config  # type: ignore[import-not-found]
import psycopg  # type: ignore[import-not-found]

from loader.pdf_document import (
    PDFRejected,
    ParsedDocument,
    parse_document,
    passage_text,
)
from shared.embeddings import (
    EXPECTED_DIMENSION,
    MODEL_NAME,
    embedding_model,
    vector_literal,
)

CONTENT_TYPE = "application/pdf"


class UploadUnavailable(RuntimeError):
    """An infrastructure failure whose generic message is safe to expose locally."""

    def __init__(self) -> None:
        super().__init__("La carga no está disponible temporalmente.")


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("Falta configuración requerida")
    return value


def _s3_client() -> Any:
    # This laboratory S3 endpoint is intentionally local and unsigned.
    return boto3.client(
        "s3",
        endpoint_url=_required_env("SEAWEEDFS_S3_ENDPOINT"),
        region_name="us-east-1",
        config=Config(signature_version=UNSIGNED, retries={"max_attempts": 4}),
    )


def _postgres_connection() -> Any:
    return psycopg.connect(
        host=_required_env("POSTGRES_HOST"),
        port=int(_required_env("POSTGRES_PORT")),
        dbname=_required_env("POSTGRES_DB"),
        user="rag_ingest",
        password=_required_env("RAG_INGEST_POSTGRES_PASSWORD"),
    )


def _validated_embeddings(raw_embeddings: Any, chunk_count: int) -> list[list[float]]:
    if len(raw_embeddings) != chunk_count:
        raise ValueError("Unexpected embedding count")

    embeddings: list[list[float]] = []
    for raw_embedding in raw_embeddings:
        if len(raw_embedding) != EXPECTED_DIMENSION:
            raise ValueError("Unexpected embedding dimension")
        if not all(
            isinstance(value, numbers.Real) and not isinstance(value, bool)
            for value in raw_embedding
        ):
            raise ValueError("Embedding contains a non-numeric value")
        embedding = [float(value) for value in raw_embedding]
        if not all(math.isfinite(value) for value in embedding):
            raise ValueError("Embedding contains a non-finite value")
        embeddings.append(embedding)
    return embeddings


def _embed_document(document: ParsedDocument) -> list[list[float]]:
    model = embedding_model()
    raw_embeddings = model.encode(
        [passage_text(chunk) for chunk in document.chunks],
        normalize_embeddings=True,
    )
    return _validated_embeddings(raw_embeddings, len(document.chunks))


def _store_and_verify_s3(
    client: Any, bucket: str, document: ParsedDocument, pdf_bytes: bytes
) -> None:
    existing_buckets = {
        item["Name"] for item in client.list_buckets().get("Buckets", [])
    }
    if bucket not in existing_buckets:
        client.create_bucket(Bucket=bucket)

    metadata = {
        "sha256": document.sha256,
        "document-id": document.document_id,
        "version": str(document.version),
        "pages": str(document.page_count),
    }
    client.put_object(
        Bucket=bucket,
        Key=document.object_key,
        Body=pdf_bytes,
        ContentType=CONTENT_TYPE,
        Metadata=metadata,
    )

    head = client.head_object(Bucket=bucket, Key=document.object_key)
    if head.get("ContentType") != CONTENT_TYPE:
        raise ValueError("Unexpected stored content type")
    if head.get("ContentLength") != document.byte_count:
        raise ValueError("Unexpected stored byte count")
    if head.get("Metadata", {}) != metadata:
        raise ValueError("Unexpected stored metadata")

    response = client.get_object(Bucket=bucket, Key=document.object_key)
    body = response["Body"]
    try:
        stored_bytes = body.read()
    finally:
        body.close()
    if stored_bytes != pdf_bytes:
        raise ValueError("Stored bytes differ from the upload")
    if hashlib.sha256(stored_bytes).hexdigest() != document.sha256:
        raise ValueError("Stored digest differs from the upload")


def _persist_document(
    connection: Any,
    document: ParsedDocument,
    embeddings: Sequence[Sequence[float]],
) -> str:
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO manual_documents (
                    document_id, version, title, object_key, content_type,
                    storage_status, sha256, byte_count, page_count, chunk_count,
                    embedding_model, index_status
                ) VALUES (%s, %s, %s, %s, %s, 'pending_upload', %s, %s, %s, 0, NULL, 'pending')
                ON CONFLICT (document_id, version) DO UPDATE
                SET storage_status = 'pending_upload',
                    index_status = 'pending',
                    chunk_count = 0,
                    embedding_model = NULL
                WHERE manual_documents.sha256 = EXCLUDED.sha256
                RETURNING sha256, title
                """,
                (
                    document.document_id,
                    document.version,
                    document.title,
                    document.object_key,
                    CONTENT_TYPE,
                    document.sha256,
                    document.byte_count,
                    document.page_count,
                ),
            )
            row = cursor.fetchone()
            if row is None or row[0] != document.sha256:
                raise RuntimeError("Document identity collision")
            stored_title = row[1]

            cursor.execute(
                """
                DELETE FROM manual_chunks
                WHERE document_id = %s AND version = %s
                """,
                (document.document_id, document.version),
            )
            for chunk, embedding in zip(document.chunks, embeddings, strict=True):
                cursor.execute(
                    """
                    INSERT INTO manual_chunks (
                        document_id, version, chunk_index, page, section, content,
                        object_key, embedding_model, embedding, content_sha256
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s)
                    """,
                    (
                        chunk.document_id,
                        chunk.version,
                        chunk.chunk_index,
                        chunk.page,
                        chunk.section,
                        chunk.content,
                        chunk.object_key,
                        MODEL_NAME,
                        vector_literal(embedding),
                        hashlib.sha256(chunk.content.encode("utf-8")).hexdigest(),
                    ),
                )

            cursor.execute(
                """
                UPDATE manual_documents
                SET storage_status = 'available',
                    index_status = 'indexed',
                    chunk_count = %s,
                    embedding_model = %s
                WHERE document_id = %s
                  AND version = %s
                  AND sha256 = %s
                """,
                (
                    len(document.chunks),
                    MODEL_NAME,
                    document.document_id,
                    document.version,
                    document.sha256,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Document finalization failed")
        connection.commit()
        return stored_title
    except Exception:
        connection.rollback()
        raise


def ingest_document(pdf_bytes: bytes, title: str, content_type: str) -> dict[str, Any]:
    """Validate first, then embed, verify S3, and atomically index in PostgreSQL."""

    # PDFRejected remains distinct and no infrastructure is touched for invalid input.
    document = parse_document(pdf_bytes, title, content_type)
    trace = ["pdf_validated"]

    connection: Any | None = None
    try:
        embeddings = _embed_document(document)
        trace.append("chunks_embedded")

        client = _s3_client()
        bucket = _required_env("MANUAL_BUCKET")
        _store_and_verify_s3(client, bucket, document, pdf_bytes)
        trace.extend(("s3_stored", "s3_verified"))

        connection = _postgres_connection()
        stored_title = _persist_document(connection, document, embeddings)
        trace.append("postgres_indexed")
    except PDFRejected:
        raise
    except Exception as error:
        raise UploadUnavailable() from error
    finally:
        if connection is not None:
            connection.close()

    return {
        "document_id": document.document_id,
        "version": document.version,
        "title": stored_title,
        "object_key": document.object_key,
        "sha256": document.sha256,
        "byte_count": document.byte_count,
        "page_count": document.page_count,
        "extracted_char_count": document.extracted_char_count,
        "chunk_count": len(document.chunks),
        "embedding_model": MODEL_NAME,
        "dimension": EXPECTED_DIMENSION,
        "index_status": "indexed",
        "embedding_preview": embeddings[0][:6],
        "trace": trace,
    }
