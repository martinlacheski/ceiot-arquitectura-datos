"""Shared read-only PostgreSQL connection settings for RAG data."""

from __future__ import annotations

import os
import re

from psycopg.rows import dict_row  # type: ignore[import-not-found]

_DOCUMENT_ID = re.compile(r"(?:env-x-manual|upload-[0-9a-f]{24})\Z")


def validate_document_id(document_id: str) -> str:
    """Accept only the canonical seed ID or immutable uploaded-document IDs."""

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
