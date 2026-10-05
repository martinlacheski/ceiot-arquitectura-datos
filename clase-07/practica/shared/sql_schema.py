"""Descubre el esquema de la base para Text-to-SQL, sin escribirlo en el código.

Todo sale del catálogo de PostgreSQL consultado con el mismo rol que ejecuta el
SQL generado (``ai_readonly``), así que el modelo ve exactamente lo que puede
leer:

- ``pg_class`` / ``pg_attribute``: tablas, vistas, columnas y tipos;
- ``obj_description`` / ``col_description``: los ``COMMENT ON`` que documentan
  la base en la propia base;
- ``pg_constraint``: claves primarias, foráneas (cómo hacer JOIN) y CHECK;
- ``pg_extension``: qué extensiones hay (TimescaleDB, PostGIS, pgvector);
- ``SELECT DISTINCT`` armado dinámicamente: valores reales de las columnas de
  texto con pocos valores distintos, para que el modelo no invente literales.

Si se agrega una tabla y se le da ``GRANT SELECT`` al rol, aparece sola.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import psycopg  # type: ignore[import-not-found]
from psycopg import sql  # type: ignore[import-not-found]

from shared.sql_query import _connection_settings  # type: ignore[import-not-found]

CACHE_SECONDS = 300
MAX_DISTINCT_VALUES = 20
# Valores más largos (hashes, rutas, textos) no ayudan a escribir filtros.
MAX_VALUE_CHARS = 48
TEXT_TYPES = ("text", "character varying", "character")

# Esquemas internos que nunca se describen: catálogo, TOAST y TimescaleDB.
_SYSTEM_SCHEMA_FILTER = """
    n.nspname NOT IN ('pg_catalog', 'information_schema')
    AND n.nspname NOT LIKE 'pg\\_%'
    AND n.nspname NOT LIKE '\\_timescaledb%'
    AND n.nspname NOT LIKE 'timescaledb%'
"""

# Legible por el rol actual y no perteneciente a una extensión (por ejemplo la
# tabla de sistemas de referencia que instala PostGIS).
_READABLE_USER_RELATION = """has_table_privilege(c.oid, 'SELECT')
  AND NOT EXISTS (
      SELECT 1 FROM pg_depend AS d
      WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e'
  )"""

EXTENSIONS_QUERY = """
SELECT extname AS name, extversion AS version
FROM pg_extension
WHERE extname <> 'plpgsql'
ORDER BY extname
"""

COLUMNS_QUERY = f"""
SELECT
    n.nspname AS schema,
    c.relname AS table,
    obj_description(c.oid, 'pg_class') AS table_comment,
    a.attname AS column,
    format_type(a.atttypid, a.atttypmod) AS type,
    col_description(c.oid, a.attnum) AS column_comment
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
JOIN pg_attribute AS a
  ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND {_SYSTEM_SCHEMA_FILTER}
  AND {_READABLE_USER_RELATION}
ORDER BY n.nspname, c.relname, a.attnum
"""

CONSTRAINTS_QUERY = f"""
SELECT
    n.nspname AS schema,
    c.relname AS table,
    pg_get_constraintdef(k.oid) AS definition
FROM pg_constraint AS k
JOIN pg_class AS c ON c.oid = k.conrelid
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE k.contype IN ('p', 'f', 'c')
  AND {_SYSTEM_SCHEMA_FILTER}
  AND {_READABLE_USER_RELATION}
ORDER BY n.nspname, c.relname, k.contype DESC, k.conname
"""


class SchemaUnavailable(RuntimeError):
    """No se pudo leer el esquema de la base."""


@dataclass(frozen=True, slots=True)
class SchemaSnapshot:
    extensions: list[dict[str, Any]] = field(default_factory=list)
    columns: list[dict[str, Any]] = field(default_factory=list)
    constraints: list[dict[str, Any]] = field(default_factory=list)
    values: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SchemaPrompt:
    text: str
    source: str  # "database": siempre se lee de la base


_cache: tuple[float, SchemaPrompt] | None = None


def clear_cache() -> None:
    global _cache
    _cache = None


def _with_comment(text: str, comment: str | None) -> str:
    return f"{text} -- {comment}" if comment else text


def format_schema(snapshot: SchemaSnapshot) -> str:
    extensions = ", ".join(
        f"{item['name']} {item['version']}" for item in snapshot.extensions
    )
    lines = [f"PostgreSQL con extensiones: {extensions or '(ninguna)'}", ""]

    lines.append("Tablas y vistas que podés leer:")
    current = None
    for column in snapshot.columns:
        relation = f"{column['schema']}.{column['table']}"
        if relation != current:
            current = relation
            lines.append(_with_comment(relation, column["table_comment"]))
        lines.append(
            "  " + _with_comment(f"{column['column']} {column['type']}", column["column_comment"])
        )

    if snapshot.constraints:
        lines += ["", "Claves y restricciones:"]
        lines += [
            f"  {item['schema']}.{item['table']}: {item['definition']}"
            for item in snapshot.constraints
        ]

    if snapshot.values:
        lines += ["", "Valores presentes en columnas de texto (exactos, distinguen mayúsculas):"]
        lines += [
            f"  {name}: {', '.join(found)}" for name, found in snapshot.values.items()
        ]
    return "\n".join(lines)


def _distinct_values(
    connection: psycopg.Connection, columns: list[dict[str, Any]]
) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for column in columns:
        if not str(column["type"]).startswith(TEXT_TYPES):
            continue
        query = sql.SQL(
            "SELECT DISTINCT {col} FROM {schema}.{table} "
            "WHERE {col} IS NOT NULL ORDER BY 1 LIMIT {limit}"
        ).format(
            col=sql.Identifier(column["column"]),
            schema=sql.Identifier(column["schema"]),
            table=sql.Identifier(column["table"]),
            limit=sql.Literal(MAX_DISTINCT_VALUES + 1),
        )
        try:
            # Un savepoint por columna: si una tabla grande supera el timeout,
            # se omiten sus valores sin abortar el resto de la lectura.
            with connection.transaction():
                rows = connection.execute(query).fetchall()
        except psycopg.Error:
            continue
        found = [str(next(iter(row.values()))) for row in rows]
        if 0 < len(found) <= MAX_DISTINCT_VALUES and all(
            len(value) <= MAX_VALUE_CHARS for value in found
        ):
            values[f"{column['schema']}.{column['table']}.{column['column']}"] = found
    return values


def _load_from_database() -> SchemaSnapshot:
    settings = {**_connection_settings(), "autocommit": False}
    with psycopg.connect(**settings) as connection:
        try:
            connection.execute("SET TRANSACTION READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '500ms'")
            connection.execute("SET LOCAL search_path = public, pg_catalog")
            extensions = connection.execute(EXTENSIONS_QUERY).fetchall()
            columns = [dict(row) for row in connection.execute(COLUMNS_QUERY).fetchall()]
            constraints = connection.execute(CONSTRAINTS_QUERY).fetchall()
            values = _distinct_values(connection, columns)
        finally:
            connection.rollback()
    return SchemaSnapshot(
        extensions=[dict(row) for row in extensions],
        columns=columns,
        constraints=[dict(row) for row in constraints],
        values=values,
    )


def schema_prompt() -> SchemaPrompt:
    """Devuelve el esquema descubierto, cacheado unos minutos."""

    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < CACHE_SECONDS:
        return _cache[1]
    try:
        snapshot = _load_from_database()
    except (psycopg.Error, KeyError, RuntimeError, TimeoutError) as error:
        raise SchemaUnavailable("No se pudo leer el esquema de la base.") from error
    prompt = SchemaPrompt(format_schema(snapshot), "database")
    _cache = (now, prompt)
    return prompt
