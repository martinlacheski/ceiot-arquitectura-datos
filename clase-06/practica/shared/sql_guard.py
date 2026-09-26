"""Frontera estructural estricta para SQL generado en la práctica."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Never

from sqlglot import exp, parse  # type: ignore[import-not-found]
from sqlglot.errors import ParseError  # type: ignore[import-not-found]

MAX_LIMIT = 50
MAX_SQL_CHARS = 4_000
ALLOWED_VIEWS = {
    "measurements": {
        "device_id",
        "measured_at",
        "variable",
        "value",
        "unit",
        "quality",
        "location_id",
    },
    "devices": {
        "device_id",
        "model",
        "location_id",
        "depends_on_device_id",
    },
    "locations": {
        "location_id",
        "name",
        "building",
    },
}
# Únicas unidades de tiempo relativo admitidas junto a now(). El literal del
# INTERVAL debe ser un entero de hasta 3 dígitos (sin signo, sin expresiones).
ALLOWED_INTERVAL_UNITS = {"HOUR", "HOURS", "DAY", "DAYS", "MINUTE", "MINUTES"}
_INTERVAL_VALUE_PATTERN = re.compile(r"^[0-9]{1,3}$")
ALLOWED_FUNCTIONS = (exp.Avg, exp.Count, exp.Min, exp.Max, exp.Sum)
ALLOWED_NODES = (
    exp.Select,
    exp.Alias,
    exp.Column,
    exp.Table,
    exp.Identifier,
    exp.From,
    exp.Where,
    exp.Group,
    exp.Order,
    exp.Ordered,
    exp.Limit,
    exp.Literal,
    exp.Star,
    exp.Distinct,
    exp.Paren,
    exp.And,
    exp.Or,
    exp.Not,
    exp.EQ,
    exp.NEQ,
    exp.GT,
    exp.GTE,
    exp.LT,
    exp.LTE,
    exp.In,
    exp.Between,
    exp.Is,
    exp.Null,
    exp.Boolean,
    exp.Neg,
    exp.Add,
    exp.Sub,
    exp.Mul,
    exp.Div,
    exp.CurrentTimestamp,
    exp.Interval,
    exp.Var,
    *ALLOWED_FUNCTIONS,
)
ALLOWED_SELECT_ARGUMENTS = {
    "expressions",
    "from",
    "where",
    "group",
    "order",
    "limit",
    "distinct",
}


@dataclass(frozen=True, slots=True)
class ValidatedSQL:
    """SQL normalizado que sólo puede construirse atravesando ``validate_sql``."""

    sql: str
    view: str
    limit: int


class SQLRejected(ValueError):
    """Rechazo seguro y esperado de SQL fuera de la gramática del laboratorio."""

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


def _validate_limit(statement: exp.Select, sql: str) -> int:
    limit = statement.args.get("limit")
    if not isinstance(limit, exp.Limit):
        _reject("se requiere LIMIT literal entre 1 y 50", sql)
    value = limit.expression
    if not isinstance(value, exp.Literal) or not value.is_int:
        _reject("LIMIT debe ser un entero literal", sql)
    parsed = int(value.this)
    if not 1 <= parsed <= MAX_LIMIT:
        _reject("LIMIT debe estar entre 1 y 50", sql)
    return parsed


def _validate_relative_time_usage(statement: exp.Select, sql: str) -> None:
    """Restringe now()/INTERVAL a la única forma ``now() - INTERVAL '<n> unidad'``.

    ``ALLOWED_NODES`` ya deja pasar ``CurrentTimestamp``, ``Interval`` y ``Var``
    de forma genérica; esta función exige además que cada aparición tenga
    exactamente esa forma, sin subexpresiones, columnas ni funciones anidadas.
    """

    for node in statement.walk():
        if isinstance(node, exp.CurrentTimestamp):
            parent = node.parent
            if not (isinstance(parent, exp.Sub) and parent.this is node):
                _reject(
                    "now() sólo se permite como now() - INTERVAL "
                    "'<n> hours|days|minutes'",
                    sql,
                )
        elif isinstance(node, exp.Interval):
            parent = node.parent
            if not (
                isinstance(parent, exp.Sub)
                and parent.expression is node
                and isinstance(parent.this, exp.CurrentTimestamp)
            ):
                _reject(
                    "INTERVAL sólo se permite restando de now() "
                    "(now() - INTERVAL '<n> hours|days|minutes')",
                    sql,
                )
            value = node.this
            if (
                not isinstance(value, exp.Literal)
                or not value.is_string
                or not _INTERVAL_VALUE_PATTERN.fullmatch(value.this)
            ):
                _reject(
                    "el literal de INTERVAL debe ser un entero de hasta 3 dígitos",
                    sql,
                )
            unit = node.args.get("unit")
            if not isinstance(unit, exp.Var) or unit.this.upper() not in ALLOWED_INTERVAL_UNITS:
                _reject("INTERVAL sólo admite hours, days o minutes", sql)
        elif isinstance(node, exp.Var):
            parent = node.parent
            if not (isinstance(parent, exp.Interval) and parent.args.get("unit") is node):
                _reject("uso de identificador no permitido", sql)


def validate_sql(sql: str) -> ValidatedSQL:
    """Acepta sólo un SELECT directo sobre una única vista ``lab_read``.

    La política es deliberadamente más chica que SQL: sin CTE, joins, uniones,
    subconsultas, comentarios, catálogos ni funciones fuera de cinco agregados.
    Ante una consulta realista no representable, el llamador debe rechazarla.
    """

    if not isinstance(sql, str) or not sql.strip():
        _reject("la consulta está vacía", sql if isinstance(sql, str) else "")
    if len(sql) > MAX_SQL_CHARS:
        _reject(f"la consulta supera {MAX_SQL_CHARS} caracteres", sql)
    if "--" in sql or "/*" in sql or "*/" in sql:
        _reject("no se permiten comentarios", sql)

    try:
        statements = parse(sql, read="postgres")
    except ParseError as error:
        _reject(f"SQL PostgreSQL inválido ({error.errors[0]['description']})", sql)

    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        _reject("se permite exactamente una sentencia SELECT", sql)
    statement = statements[0]

    select_count = sum(1 for _ in statement.find_all(exp.Select))
    if select_count != 1:
        _reject("no se permiten subconsultas", sql)

    if statement.args.get("with") is not None:
        _reject("no se permiten CTE", sql)

    unexpected_arguments = {
        name
        for name, value in statement.args.items()
        if value and name not in ALLOWED_SELECT_ARGUMENTS
    }
    if unexpected_arguments:
        names = ", ".join(sorted(unexpected_arguments))
        _reject(f"la forma de SELECT solicitada no está permitida ({names})", sql)

    tables = list(statement.find_all(exp.Table))
    if len(tables) != 1:
        _reject("se requiere exactamente una vista directa", sql)
    table = tables[0]
    if table.catalog or table.db != "lab_read" or table.name not in ALLOWED_VIEWS:
        _reject("sólo se permiten lab_read.measurements o lab_read.devices", sql)

    for node in statement.walk():
        if not isinstance(node, ALLOWED_NODES):
            _reject(f"la construcción {type(node).__name__} no está permitida", sql)

    for function in statement.find_all(exp.Func):
        if not isinstance(function, (*ALLOWED_FUNCTIONS, exp.CurrentTimestamp)):
            _reject(f"la función {function.sql_name()} no está permitida", sql)

    _validate_relative_time_usage(statement, sql)

    view = table.name
    table_aliases = {view}
    if table.alias:
        table_aliases.add(table.alias)
    output_aliases = {
        alias.alias for alias in statement.find_all(exp.Alias) if alias.alias
    }
    for column in statement.find_all(exp.Column):
        if len(column.parts) > 2:
            _reject("las columnas no pueden usar catálogo o esquema", sql)
        if column.table and column.table not in table_aliases:
            _reject("la columna usa una relación no permitida", sql)
        if column.name not in ALLOWED_VIEWS[view] | output_aliases:
            _reject(f"la columna {column.name!r} no está expuesta", sql)

    limit_value = _validate_limit(statement, sql)
    return ValidatedSQL(
        sql=statement.sql(dialect="postgres"),
        view=view,
        limit=limit_value,
    )
