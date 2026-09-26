"""Ejecución acotada de consultas aprobadas por :mod:`sql_guard`."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import psycopg  # type: ignore[import-not-found]
from psycopg.rows import dict_row  # type: ignore[import-not-found]

from shared.sql_guard import (  # type: ignore[import-not-found]
    ValidatedSQL,
    validate_sql,
)

AI_ROLE = "ai_readonly"
MAX_RESULT_ROWS = 50
MAX_RESULT_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    byte_count: int


class ResultLimitExceeded(RuntimeError):
    """El resultado excede un límite local aunque la consulta fuese válida."""


def _connection_settings() -> dict[str, object]:
    user = os.getenv("AI_POSTGRES_USER", AI_ROLE)
    if user != AI_ROLE:
        raise RuntimeError(
            "La ejecución Text-to-SQL exige el rol local restringido ai_readonly"
        )
    return {
        "host": os.getenv("POSTGRES_HOST", "postgres"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "ceiot_class6"),
        "user": user,
        # Compose inyecta la credencial fija, pública y exclusiva de la demo.
        "password": os.environ["AI_POSTGRES_PASSWORD"],
        "connect_timeout": 3,
        "autocommit": True,
        "row_factory": dict_row,
    }


def execute_validated_sql(validated: ValidatedSQL) -> QueryResult:
    """Ejecuta SQL validado como ``ai_readonly`` y siempre revierte la sesión."""

    if not isinstance(validated, ValidatedSQL):
        raise TypeError("execute_validated_sql requiere un objeto ValidatedSQL")

    # No confiar sólo en el tipo: vuelve a validar si un llamador construyó la
    # dataclass manualmente o si cambió la política entre generación y uso.
    checked = validate_sql(validated.sql)

    with psycopg.connect(**_connection_settings()) as connection:
        connection.execute("BEGIN READ ONLY")
        try:
            connection.execute("SET LOCAL statement_timeout = '1500ms'")
            connection.execute("SET LOCAL lock_timeout = '250ms'")
            connection.execute(
                "SET LOCAL idle_in_transaction_session_timeout = '2000ms'"
            )
            connection.execute("SET LOCAL search_path = pg_catalog")

            cursor = connection.execute(checked.sql)
            rows = cursor.fetchmany(MAX_RESULT_ROWS + 1)
            if len(rows) > MAX_RESULT_ROWS:
                raise ResultLimitExceeded(
                    f"El resultado supera el máximo de {MAX_RESULT_ROWS} filas"
                )

            byte_count = 0
            safe_rows: list[dict[str, Any]] = []
            for row in rows:
                row_bytes = len(
                    json.dumps(row, default=str, ensure_ascii=False).encode("utf-8")
                )
                if byte_count + row_bytes > MAX_RESULT_BYTES:
                    raise ResultLimitExceeded(
                        f"El resultado supera el máximo de {MAX_RESULT_BYTES} bytes"
                    )
                byte_count += row_bytes
                safe_rows.append(dict(row))

            columns = tuple(
                description.name for description in (cursor.description or ())
            )
            return QueryResult(columns, tuple(safe_rows), byte_count)
        finally:
            connection.execute("ROLLBACK")
