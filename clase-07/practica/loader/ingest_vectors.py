#!/usr/bin/env python3
"""Indexa en pgvector el manual PDF que ya está almacenado en SeaweedFS S3."""

from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass
from typing import Any

import boto3  # type: ignore[import-not-found]
import psycopg  # type: ignore[import-not-found]
from botocore import UNSIGNED  # type: ignore[import-not-found]
from botocore.config import Config  # type: ignore[import-not-found]
from pypdf import PdfReader  # type: ignore[import-not-found]

from shared.embeddings import (  # type: ignore[import-not-found]
    EMBEDDING_BATCH_SIZE,
    MODEL_NAME,
    embedding_model,
    vector_literal,
)

SEED_DOCUMENT_ID = "env-x-manual"

EXPECTED_SECTIONS = (
    (1, "Preparación y condiciones"),
    (1, "Recalibración tras reemplazo de batería"),
    (2, "Comprobación"),
    (2, "Recuperación segura"),
)


@dataclass(frozen=True)
class Chunk:
    document_id: str
    version: int
    page: int
    section: str
    chunk_index: int
    content: str
    object_key: str


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Falta la variable requerida {name}")
    return value


def postgres_connection() -> psycopg.Connection[Any]:
    return psycopg.connect(
        host=required_env("POSTGRES_HOST"),
        port=int(required_env("POSTGRES_PORT")),
        user=required_env("POSTGRES_USER"),
        password=required_env("POSTGRES_PASSWORD"),
        dbname=required_env("POSTGRES_DB"),
    )


def s3_client():
    # El laboratorio usa S3 local sin credenciales; no heredar ni buscar claves.
    return boto3.client(
        "s3",
        endpoint_url=required_env("SEAWEEDFS_S3_ENDPOINT"),
        region_name="us-east-1",
        config=Config(signature_version=UNSIGNED, retries={"max_attempts": 4}),
    )


def read_available_document(connection: psycopg.Connection[Any]) -> tuple[str, int, str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT document_id, version, object_key
            FROM manual_documents
            WHERE document_id = %s
              AND storage_status = 'available'
            ORDER BY version DESC
            LIMIT 1
            """,
            (SEED_DOCUMENT_ID,),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError(
            f"El manual seed {SEED_DOCUMENT_ID!r} no está disponible para indexar"
        )
    return row[0], row[1], row[2]


def download_pdf(document_id: str, version: int, object_key: str) -> bytes:
    client = s3_client()
    bucket = required_env("MANUAL_BUCKET")
    head = client.head_object(Bucket=bucket, Key=object_key)
    metadata = head.get("Metadata", {})
    validate_object_provenance(metadata, document_id, version)

    response = client.get_object(Bucket=bucket, Key=object_key)
    try:
        pdf_bytes = response["Body"].read()
    finally:
        response["Body"].close()
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("El objeto S3 no contiene bytes de un PDF")
    digest = metadata.get("sha256")
    if digest and hashlib.sha256(pdf_bytes).hexdigest() != digest:
        raise ValueError("La huella del PDF no coincide con los metadatos S3")
    return pdf_bytes


def validate_object_provenance(metadata: dict[str, str], document_id: str, version: int) -> None:
    """Impide asociar vectores a otra versión aunque la clave S3 sea válida."""
    if metadata.get("document-id") != document_id:
        raise ValueError("El document_id de S3 no coincide con PostgreSQL")
    if metadata.get("version") != str(version):
        raise ValueError("La versión de S3 no coincide con PostgreSQL")
    if metadata.get("pages") != "2":
        raise ValueError("El objeto S3 no declara las dos páginas esperadas")


def _clean_lines(page_text: str) -> list[str]:
    ignored_prefixes = ("Manual de calibración", "Documento ", "Proveniencia:")
    return [
        line.strip()
        for line in page_text.splitlines()
        if line.strip() and not line.strip().startswith(ignored_prefixes)
    ]


def chunks_from_page_texts(
    page_texts: list[str], document_id: str, version: int, object_key: str
) -> list[Chunk]:
    """Forma un chunk semántico por sección, sin usar la fuente JSON del PDF."""
    if len(page_texts) != 2:
        raise ValueError("El PDF debe contener exactamente dos páginas")

    chunks: list[Chunk] = []
    for page_number, page_text in enumerate(page_texts, start=1):
        expected = [section for page, section in EXPECTED_SECTIONS if page == page_number]
        lines = _clean_lines(page_text)
        positions: list[int] = []
        for section in expected:
            try:
                positions.append(lines.index(section))
            except ValueError as error:
                raise ValueError(
                    f"No se encontró la sección {section!r} en la página {page_number}"
                ) from error

        for position, section in zip(positions, expected, strict=True):
            next_positions = [candidate for candidate in positions if candidate > position]
            end = min(next_positions) if next_positions else len(lines)
            content = " ".join(lines[position + 1 : end]).strip()
            if len(content.split()) < 8:
                raise ValueError(f"La sección {section!r} no contiene texto significativo")
            chunks.append(
                Chunk(
                    document_id=document_id,
                    version=version,
                    page=page_number,
                    section=section,
                    chunk_index=len(chunks),
                    content=content,
                    object_key=object_key,
                )
            )

    if len(chunks) != 4:
        raise ValueError("El manual debe producir exactamente cuatro chunks de sección")
    return chunks


def extract_chunks(pdf_bytes: bytes, document_id: str, version: int, object_key: str) -> list[Chunk]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return chunks_from_page_texts(
        [page.extract_text() or "" for page in reader.pages],
        document_id,
        version,
        object_key,
    )


def passage_text(chunk: Chunk) -> str:
    """Texto de pasaje del chunk específico del loader; bge-m3 no usa prefijos."""

    return f"{chunk.section}. {chunk.content}"


def store_chunks(
    connection: psycopg.Connection[Any], chunks: list[Chunk], embeddings: Any, model_name: str
) -> None:
    if len(chunks) != len(embeddings):
        raise ValueError("La cantidad de embeddings no coincide con los chunks")
    with connection.cursor() as cursor:
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            cursor.execute(
                """
                INSERT INTO manual_chunks (
                    document_id, version, chunk_index, page, section, content,
                    object_key, embedding_model, embedding, content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s)
                ON CONFLICT (document_id, version, chunk_index) DO UPDATE
                SET page = EXCLUDED.page,
                    section = EXCLUDED.section,
                    content = EXCLUDED.content,
                    object_key = EXCLUDED.object_key,
                    embedding_model = EXCLUDED.embedding_model,
                    embedding = EXCLUDED.embedding,
                    content_sha256 = EXCLUDED.content_sha256,
                    indexed_at = now()
                """,
                (
                    chunk.document_id,
                    chunk.version,
                    chunk.chunk_index,
                    chunk.page,
                    chunk.section,
                    chunk.content,
                    chunk.object_key,
                    model_name,
                    vector_literal(embedding),
                    hashlib.sha256(chunk.content.encode("utf-8")).hexdigest(),
                ),
            )

        document = chunks[0] if chunks else None
        if document is None:
            raise ValueError("No hay chunks para marcar como indexados")
        cursor.execute(
            """
            UPDATE manual_documents
            SET chunk_count = %s,
                embedding_model = %s,
                index_status = 'indexed'
            WHERE document_id = %s
              AND version = %s
              AND object_key = %s
            """,
            (
                len(chunks),
                model_name,
                document.document_id,
                document.version,
                document.object_key,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("No se pudo marcar exactamente un manual como indexado")
    connection.commit()


def main() -> None:
    model_name: str = MODEL_NAME

    with postgres_connection() as connection:
        document_id, version, object_key = read_available_document(connection)
        pdf_bytes = download_pdf(document_id, version, object_key)
        chunks = extract_chunks(pdf_bytes, document_id, version, object_key)

        print(f"Cargando modelo local {model_name}; la primera descarga puede tardar.")
        model = embedding_model()
        embeddings: list[Any] = []
        for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
            embeddings.extend(
                model.encode(
                    [passage_text(chunk) for chunk in batch],
                    normalize_embeddings=True,
                )
            )
        store_chunks(connection, chunks, embeddings, model_name)

    print(
        f"Indexación completa: {len(chunks)} chunks de {document_id} v{version}, "
        f"origen s3://{required_env('MANUAL_BUCKET')}/{object_key}."
    )


if __name__ == "__main__":
    main()
