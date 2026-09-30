"""Descripción del esquema para Text-to-SQL leída desde la base.

En lugar de escribir las vistas a mano, se consultan como ``ai_readonly``:
``information_schema.columns`` da la estructura de ``lab_read`` (sólo lo que ese
rol puede ver) y ``SELECT DISTINCT`` da los valores reales que el modelo debe
respetar. Las reglas de tiempo y de mayúsculas no están en la base: dependen
del validador, por eso siguen escritas en el código.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg  # type: ignore[import-not-found]

from shared.sql_query import _connection_settings  # type: ignore[import-not-found]

STATIC_SQL_SCHEMA = """lab_read.measurements(
  device_id text, measured_at timestamptz, variable text, value numeric,
  unit text, quality text, location_id text
)
lab_read.devices(
  device_id text, model text, location_id text, depends_on_device_id text
)
lab_read.locations(
  location_id text, name text, building text
)
Valores exactos conocidos (respetá mayúsculas y minúsculas):
- variable: co2, temperature, humidity
- quality: GOOD, SUSPECT
- device_id: AIR-002, AMB-001, ACT-003, AMB-005
- model: ENV-X (AMB-001 y AMB-005), AirQuality-Pro (AIR-002)
- location_id: AULA-204, LAB-101, CIUDAD-UNIV
- lab_read.locations.name: Aula 204, Laboratorio 101, Ciudad Universitaria
Las comparaciones de texto en PostgreSQL son case-sensitive: nunca conviertas co2 a CO2.
Predicado seguro de ejemplo: variable = 'co2'; location_id = 'AULA-204'.
Hay datos recientes de ENV-X (AMB-001) para las últimas 48 horas relativas a
now(): usá now() - INTERVAL '<n> hours|days|minutes' (esa es la ÚNICA forma de
tiempo relativo admitida) cuando la pregunta pida un período reciente, por
ejemplo measured_at >= now() - INTERVAL '24 hours'. Como valor secundario, y
sólo si la pregunta pide una fecha histórica exacta, también existen ocho
mediciones fijas del día UTC 2025-05-12T00:00:00Z a 2025-05-13T00:00:00Z."""

RULES = """Las comparaciones de texto en PostgreSQL son case-sensitive: usá los valores exactamente como figuran arriba.
Para períodos recientes usá now() - INTERVAL '<n> hours|days|minutes' (esa es la ÚNICA forma de
tiempo relativo admitida), por ejemplo measured_at >= now() - INTERVAL '24 hours'."""

COLUMNS_QUERY = """
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'lab_read'
ORDER BY table_name, ordinal_position
"""

# Consultas fijas escritas por el código (no por el modelo) para obtener los
# valores reales de las columnas que suelen usarse en filtros.
VALUE_QUERIES = {
    "variable": "SELECT DISTINCT variable FROM lab_read.measurements ORDER BY 1",
    "quality": "SELECT DISTINCT quality FROM lab_read.measurements ORDER BY 1",
    "device_id": "SELECT DISTINCT device_id FROM lab_read.devices ORDER BY 1",
    "model": "SELECT DISTINCT model FROM lab_read.devices ORDER BY 1",
    "location_id": "SELECT DISTINCT location_id FROM lab_read.locations ORDER BY 1",
    "location_name": "SELECT DISTINCT name FROM lab_read.locations ORDER BY 1",
}
VALUE_LABELS = {"location_name": "lab_read.locations.name"}


@dataclass(frozen=True, slots=True)
class SchemaPrompt:
    text: str
    source: str  # "database" o "static"


_cached: SchemaPrompt | None = None


def clear_cache() -> None:
    global _cached
    _cached = None


def format_schema(
    columns: list[dict[str, Any]], values: dict[str, list[str]]
) -> str:
    views: dict[str, list[str]] = {}
    for column in columns:
        views.setdefault(column["table_name"], []).append(
            f"{column['column_name']} {column['data_type']}"
        )
    lines = [
        f"lab_read.{view}(\n  {', '.join(view_columns)}\n)"
        for view, view_columns in views.items()
    ]
    lines.append("Valores exactos presentes en la base:")
    for name, found in values.items():
        label = VALUE_LABELS.get(name, name)
        lines.append(f"- {label}: {', '.join(found) if found else '(sin datos)'}")
    lines.append(RULES)
    return "\n".join(lines)


def _load_from_database() -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    with psycopg.connect(**_connection_settings()) as connection:
        connection.execute("BEGIN READ ONLY")
        try:
            connection.execute("SET LOCAL statement_timeout = '1500ms'")
            columns = connection.execute(COLUMNS_QUERY).fetchall()
            values = {
                name: [str(next(iter(row.values()))) for row in connection.execute(query).fetchall()]
                for name, query in VALUE_QUERIES.items()
            }
        finally:
            connection.execute("ROLLBACK")
    return [dict(row) for row in columns], values


def schema_prompt() -> SchemaPrompt:
    """Devuelve el esquema leído de la base, o el texto fijo si no responde."""

    global _cached
    if _cached is not None:
        return _cached
    try:
        columns, values = _load_from_database()
    except (psycopg.Error, KeyError, RuntimeError, TimeoutError):
        return SchemaPrompt(STATIC_SQL_SCHEMA, "static")
    # Sin seed las listas vienen vacías: se usa el texto fijo y no se cachea,
    # para volver a leer la base cuando ya tenga datos.
    if not columns or not any(values.values()):
        return SchemaPrompt(STATIC_SQL_SCHEMA, "static")
    _cached = SchemaPrompt(format_schema(columns, values), "database")
    return _cached
