"""Ejecución acotada de SQL generado, con la base como frontera de seguridad."""

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
    # True cuando había más filas (o bytes) que el máximo y se recortaron.
    truncated: bool = False


def _connection_settings() -> dict[str, object]:
    user = os.getenv("AI_POSTGRES_USER", AI_ROLE)
    if user != AI_ROLE:
        raise RuntimeError(
            "La ejecución Text-to-SQL exige el rol local restringido ai_readonly"
        )
    return {
        "host": os.getenv("POSTGRES_HOST", "postgres"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "ceiot_class7"),
        "user": user,
        # Compose inyecta la credencial fija, pública y exclusiva de la demo.
        "password": os.environ["AI_POSTGRES_PASSWORD"],
        "connect_timeout": 3,
        "autocommit": True,
        "row_factory": dict_row,
    }


def execute_validated_sql(validated: ValidatedSQL) -> QueryResult:
    """Ejecuta SQL de lectura como ``ai_readonly`` y siempre revierte la sesión.

    Los límites los pone la base: rol sin escritura, transacción READ ONLY y
    timeouts. Acá sólo se acota cuánto resultado se devuelve a la API.
    """

    if not isinstance(validated, ValidatedSQL):
        raise TypeError("execute_validated_sql requiere un objeto ValidatedSQL")

    # No confiar sólo en el tipo: vuelve a validar por si un llamador construyó
    # la dataclass a mano.
    checked = validate_sql(validated.sql)

    with psycopg.connect(**_connection_settings()) as connection:
        connection.execute("BEGIN READ ONLY")
        try:
            connection.execute("SET LOCAL statement_timeout = '1500ms'")
            connection.execute("SET LOCAL lock_timeout = '250ms'")
            connection.execute(
                "SET LOCAL idle_in_transaction_session_timeout = '2000ms'"
            )
            connection.execute("SET LOCAL work_mem = '16MB'")
            connection.execute("SET LOCAL search_path = public, pg_catalog")

            cursor = connection.execute(checked.sql)
            rows = cursor.fetchmany(MAX_RESULT_ROWS + 1)
            truncated = len(rows) > MAX_RESULT_ROWS

            byte_count = 0
            safe_rows: list[dict[str, Any]] = []
            for row in rows[:MAX_RESULT_ROWS]:
                row_bytes = len(
                    json.dumps(row, default=str, ensure_ascii=False).encode("utf-8")
                )
                if byte_count + row_bytes > MAX_RESULT_BYTES:
                    truncated = True
                    break
                byte_count += row_bytes
                safe_rows.append(dict(row))

            columns = tuple(
                description.name for description in (cursor.description or ())
            )
            return QueryResult(columns, tuple(safe_rows), byte_count, truncated)
        finally:
            connection.execute("ROLLBACK")
