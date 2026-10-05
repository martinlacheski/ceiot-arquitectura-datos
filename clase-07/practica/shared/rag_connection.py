"""Shared read-only PostgreSQL connection settings for RAG data."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg  # type: ignore[import-not-found]
from psycopg.rows import dict_row  # type: ignore[import-not-found]

from shared.document_identity import checked_organization_id

_DOCUMENT_ID = re.compile(r"upload-[0-9a-f]{24}\Z")


def validate_document_id(document_id: str) -> str:
    """Accept only immutable uploaded-document IDs."""

    if not isinstance(document_id, str) or _DOCUMENT_ID.fullmatch(document_id) is None:
        raise ValueError("document_id no tiene un formato válido")
    return document_id


def rag_connection_settings() -> dict[str, object]:
    """Return settings pinned to the least-privileged RAG reader role."""

    configured_user = os.getenv("RAG_POSTGRES_USER", "rag_readonly")
    if configured_user != "rag_readonly":
        raise RuntimeError("La recuperación exige el rol restringido rag_readonly")
    return {
        "host": os.getenv("POSTGRES_HOST", "postgres"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "ceiot_class7"),
        "user": "rag_readonly",
        "password": os.environ["RAG_POSTGRES_PASSWORD"],
        "connect_timeout": 3,
        "autocommit": True,
        "row_factory": dict_row,
    }


@contextmanager
def tenant_cursor(tenant_id: int) -> Iterator[Any]:
    """Cursor de ``rag_readonly`` con el contexto de la organización ya fijado.

    ``set_config('app.tenant_id', ..., true)`` vale sólo dentro de una
    transacción, y la conexión está en autocommit: por eso se abre una
    transacción explícita y el contexto se fija ANTES de cualquier consulta.
    Las políticas RLS de ``manual_documents`` y ``manual_chunks`` hacen el resto:
    una fila de otra organización no existe para este cursor.
    """

    organization = checked_organization_id(tenant_id)
    with (
        psycopg.connect(**rag_connection_settings()) as connection,
        connection.transaction(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)", (str(organization),)
        )
        yield cursor
