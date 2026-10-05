"""Control mínimo para SQL generado: una única sentencia de lectura.

En el modo abierto el modelo puede usar todo el SQL de PostgreSQL (JOIN,
subconsultas, CTE, funciones de ventana, TimescaleDB, PostGIS). La seguridad
real la aplica la base: el rol ``ai_readonly`` sólo tiene SELECT, la
transacción es READ ONLY y hay timeouts. Este control sólo rechaza temprano,
con un mensaje claro, lo que nunca puede ser una lectura.
"""

from __future__ import annotations

import json
import re
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


# El aislamiento entre organizaciones (RLS) depende de la variable de sesión
# app.tenant_id, que CUALQUIER rol puede cambiar con set_config. Si el SQL
# generado pudiera llamarla, un modelo (o una inyección de prompt) elegiría el
# tenant que quiera. Se rechaza todo lo que cambie o lea el contexto, o que
# ejecute SQL armado como texto (query_to_xml, dblink) y así lo esconda.
#
# La búsqueda es textual, sobre el SQL sin comillas dobles, y corre
# ANTES del análisis: atrapa también sintaxis que sqlglot no entiende.
_FORBIDDEN_CALL = re.compile(
    r"\b(set_config|current_setting|pg_reload_conf|dblink\w*"
    r"|query_to_xml\w*|cursor_to_xml\w*)\b",
    re.IGNORECASE,
)
_SQL_COMMENT = re.compile(r"/\*.*?\*/|--[^\n]*", re.DOTALL)
# U&"..." escribe un identificador con secuencias \XXXX: permitiría escribir
# set_config sin que aparezca literalmente.
_UNICODE_ESCAPED_IDENTIFIER = re.compile(r"\bu&\s*\"", re.IGNORECASE)
# Si sqlglot no puede analizar la sentencia, al menos debe empezar como lectura.
_READ_START = re.compile(r"^[\s(]*(select|with|values|table)\b", re.IGNORECASE)


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


def _reject_context_tampering(sql: str) -> None:
    # Se busca en el texto completo, comentarios incluidos: quitar comentarios
    # con una regex permitiría esconder la llamada tras un literal con "--".
    if _UNICODE_ESCAPED_IDENTIFIER.search(sql):
        _reject("no se permiten identificadores con escapes Unicode (U&\"...\")", sql)
    # Sin comillas: "set_config"(...) y pg_catalog."set_config"(...) también caen.
    normalized = sql.replace('"', "")
    found = _FORBIDDEN_CALL.search(normalized)
    if found:
        _reject(
            f"{found.group(1).lower()} no está permitido: podría alterar el contexto "
            "de la organización",
            sql,
        )


def validate_sql(sql: str) -> ValidatedSQL:
    """Acepta exactamente una consulta de lectura; el resto lo decide la base."""

    if not isinstance(sql, str) or not sql.strip():
        _reject("la consulta está vacía", sql if isinstance(sql, str) else "")
    if len(sql) > MAX_SQL_CHARS:
        _reject(f"la consulta supera {MAX_SQL_CHARS} caracteres", sql)

    _reject_context_tampering(sql)

    try:
        statements = [
            statement for statement in parse(sql, read="postgres") if statement
        ]
    except ParseError:
        # sqlglot no conoce toda la sintaxis de las extensiones (por ejemplo
        # algunos operadores de pgvector). La base igual la ejecuta en una
        # transacción READ ONLY y psycopg no admite varias sentencias juntas.
        if not _READ_START.match(_SQL_COMMENT.sub(" ", sql)):
            _reject("sólo se permiten consultas de lectura (SELECT o WITH ... SELECT)", sql)
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
