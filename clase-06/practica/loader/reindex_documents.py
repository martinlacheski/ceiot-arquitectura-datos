#!/usr/bin/env python3
"""Reindexa documentos cargados por la UI que quedaron `pending` tras un
cambio de modelo de embeddings (por ejemplo la migración a `BAAI/bge-m3`).

El manual semilla se reindexa con `python -m loader.ingest_vectors`; este
módulo cubre únicamente los PDF cargados a través de la UI
(`document_id` con prefijo `upload-`), que sólo existen en SeaweedFS y en
PostgreSQL, nunca en el disco local del loader.

Reutiliza exactamente la misma lógica de parseo (`loader.pdf_document`), de
generación de embeddings y de persistencia (`loader.pdf_storage`) que
`loader.upload_api` usa para una carga nueva, y se conecta con el mismo rol
acotado `rag_ingest` que usa el servicio `uploader`: sin credenciales de
propietario, sin acceso a `lab_read` ni a la telemetría.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

from loader import pdf_storage
from loader.pdf_document import PDFRejected, parse_document

UPLOAD_PREFIX = "upload-"


@dataclass(frozen=True)
class PendingDocument:
    document_id: str
    version: int
    title: str
    object_key: str


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Falta la variable requerida {name}")
    return value


def pending_uploaded_documents(connection: Any) -> list[PendingDocument]:
    """Lista documentos cargados por la UI, disponibles pero no indexados."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT document_id, version, title, object_key
            FROM manual_documents
            WHERE storage_status = 'available'
              AND index_status <> 'indexed'
              AND document_id LIKE %s
            ORDER BY document_id, version
            """,
            (f"{UPLOAD_PREFIX}%",),
        )
        return [
            PendingDocument(
                document_id=row[0],
                version=row[1],
                title=row[2],
                object_key=row[3],
            )
            for row in cursor.fetchall()
        ]


def _download_pdf(client: Any, bucket: str, object_key: str) -> bytes:
    response = client.get_object(Bucket=bucket, Key=object_key)
    try:
        return response["Body"].read()
    finally:
        response["Body"].close()


def reindex_document(
    connection: Any, client: Any, bucket: str, pending: PendingDocument
) -> dict[str, Any]:
    """Descarga, re-parsea, re-embebe y persiste un documento pendiente.

    Reusa `parse_document` (recalcula identidad e integridad desde los bytes
    descargados), `pdf_storage._embed_document` y
    `pdf_storage._persist_document`, exactamente el mismo camino que una
    carga nueva por la UI.
    """

    pdf_bytes = _download_pdf(client, bucket, pending.object_key)
    document = parse_document(pdf_bytes, pending.title, "application/pdf")

    if document.document_id != pending.document_id or document.object_key != pending.object_key:
        raise ValueError(
            "el objeto descargado no coincide con la identidad registrada "
            "(hash distinto); no se reindexa"
        )

    embeddings = pdf_storage._embed_document(document)
    pdf_storage._persist_document(connection, document, embeddings)
    return {
        "document_id": document.document_id,
        "version": document.version,
        "chunk_count": len(document.chunks),
    }


def main() -> None:
    connection = pdf_storage._postgres_connection()
    client = pdf_storage._s3_client()
    bucket = _required_env("MANUAL_BUCKET")

    succeeded: list[dict[str, Any]] = []
    failed: list[tuple[str, str]] = []
    try:
        pending = pending_uploaded_documents(connection)
        # rag_ingest has a short idle_in_transaction_session_timeout; close
        # the implicit read transaction now so it does not expire while we
        # download from S3 and run the (possibly slow, first-load) model.
        connection.commit()
        if not pending:
            print("No hay documentos cargados por la UI pendientes de reindexar.")
            return

        for document in pending:
            try:
                result = reindex_document(connection, client, bucket, document)
                succeeded.append(result)
                print(
                    f"Reindexado {result['document_id']} v{result['version']}: "
                    f"{result['chunk_count']} chunks."
                )
            except PDFRejected as error:
                failed.append((document.document_id, error.reason))
            except Exception as error:  # noqa: BLE001 - reported, never swallowed
                failed.append((document.document_id, str(error)))
    finally:
        connection.close()

    print(
        f"Reindexación completa: {len(succeeded)} documento(s) reindexado(s), "
        f"{len(failed)} fallido(s)."
    )
    for document_id, reason in failed:
        print(f"  - {document_id}: {reason}", file=sys.stderr)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
