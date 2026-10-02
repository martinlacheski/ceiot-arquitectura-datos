"""Control mínimo para SQL generado: una única sentencia de lectura.

En el modo abierto el modelo puede usar todo el SQL de PostgreSQL (JOIN,
subconsultas, CTE, funciones de ventana, TimescaleDB, PostGIS). La seguridad
real la aplica la base: el rol ``ai_readonly`` sólo tiene SELECT, la
transacción es READ ONLY y hay timeouts. Este control sólo rechaza temprano,
con un mensaje claro, lo que nunca puede ser una lectura.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Never

from sqlglot import exp, parse  # type: ignore[import-not-found]
from sqlglot.errors import ParseError  # type: ignore[import-not-found]

MAX_SQL_CHARS = 4_000

# Nodos que modifican datos, esquema o sesión. Se buscan en todo el árbol para
# atrapar también un DELETE escondido dentro de un CTE o un SELECT ... INTO.
_WRITE_NODE_NAMES = (
    "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "AlterTable",
    "TruncateTable", "Command", "Set", "Copy", "Into", "Grant", "Transaction",
    "Commit", "Rollback", "Use", "Pragma",
)
_WRITE_NODES = tuple(
    getattr(exp, name) for name in _WRITE_NODE_NAMES if hasattr(exp, name)
)


@dataclass(frozen=True, slots=True)
class ValidatedSQL:
    """SQL que pasó por ``validate_sql``: una sola sentencia de lectura."""

    sql: str


class SQLRejected(ValueError):
    """Rechazo esperado y seguro de mostrar: guard o error de la base."""

    def __init__(self, reason: str, submitted_sql: str) -> None:
        self.reason = reason
        self.preview = safe_sql_preview(submitted_sql)
        super().__init__(f"Consulta rechazada: {reason}. SQL: {self.preview}")


def safe_sql_preview(sql: str, max_chars: int = 240) -> str:
    """Representa entrada no confiable en una única línea, escapada y acotada."""

    clipped = sql[:max_chars]
    if len(sql) > max_chars:
        clipped += "…"
    return json.dumps(clipped, ensure_ascii=True)


def _reject(reason: str, sql: str) -> Never:
    raise SQLRejected(reason, sql)


def validate_sql(sql: str) -> ValidatedSQL:
    """Acepta exactamente una consulta de lectura; el resto lo decide la base."""

    if not isinstance(sql, str) or not sql.strip():
        _reject("la consulta está vacía", sql if isinstance(sql, str) else "")
    if len(sql) > MAX_SQL_CHARS:
        _reject(f"la consulta supera {MAX_SQL_CHARS} caracteres", sql)

    try:
        statements = [
            statement for statement in parse(sql, read="postgres") if statement
        ]
    except ParseError:
        # sqlglot no conoce toda la sintaxis de las extensiones (por ejemplo
        # algunos operadores de pgvector). La base igual la ejecuta en una
        # transacción READ ONLY y psycopg no admite varias sentencias juntas.
        return ValidatedSQL(sql=sql.strip().rstrip(";").strip())

    if len(statements) != 1:
        _reject("se permite exactamente una sentencia de lectura", sql)
    statement = statements[0]
    if not isinstance(statement, exp.Query):
        _reject("sólo se permiten consultas de lectura (SELECT o WITH ... SELECT)", sql)
    for node in statement.walk():
        if isinstance(node, _WRITE_NODES):
            _reject(
                f"sólo se permiten consultas de lectura ({type(node).__name__} no lo es)",
                sql,
            )

    return ValidatedSQL(sql=sql.strip().rstrip(";").strip())
