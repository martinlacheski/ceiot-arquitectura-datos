from __future__ import annotations

import os
from decimal import Decimal

import psycopg  # type: ignore[import-not-found]
import pytest  # type: ignore[import-not-found]

from shared.sql_guard import (  # type: ignore[import-not-found]
    SQLRejected,
    safe_sql_preview,
    validate_sql,
)
from shared.sql_query import execute_validated_sql  # type: ignore[import-not-found]


AVERAGE_QUERY = """
SELECT AVG(value) AS average_co2
FROM lab_read.measurements
WHERE device_id = 'AIR-002'
  AND variable = 'co2'
  AND measured_at >= '2025-05-12T00:00:00Z'
  AND measured_at < '2025-05-13T00:00:00Z'
LIMIT 1
"""


def test_accepts_and_executes_known_average_for_2025_05_12() -> None:
    validated = validate_sql(AVERAGE_QUERY)

    assert validated.view == "measurements"
    assert validated.limit == 1

    result = execute_validated_sql(validated)

    assert result.columns == ("average_co2",)
    assert len(result.rows) == 1
    assert result.rows[0]["average_co2"] == pytest.approx(
        Decimal("805.6666666666666667")
    )
    assert result.byte_count < 64 * 1024


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        (
            "SELECT device_id FROM lab_read.devices LIMIT 1; "
            "SELECT device_id FROM lab_read.devices LIMIT 1",
            "exactamente una sentencia",
        ),
        (
            "WITH removed AS (DELETE FROM public.measurements RETURNING *) "
            "SELECT device_id FROM lab_read.measurements LIMIT 1",
            "no se permiten CTE",
        ),
        (
            "SELECT (SELECT pg_sleep(1)) "
            "FROM lab_read.measurements LIMIT 1",
            "subconsultas",
        ),
        (
            "SELECT rolname FROM pg_catalog.pg_roles LIMIT 1",
            "lab_read.measurements",
        ),
        (
            "SELECT device_id FROM lab_read.measurements",
            "se requiere LIMIT literal",
        ),
        (
            "SELECT device_id FROM lab_read.measurements LIMIT 51",
            "entre 1 y 50",
        ),
    ],
)
def test_rejects_adversarial_or_unbounded_sql(sql: str, reason: str) -> None:
    with pytest.raises(SQLRejected, match=reason):
        validate_sql(sql)


def test_rejects_unknown_functions_comments_joins_and_unexposed_columns() -> None:
    rejected = [
        "SELECT set_config('search_path', 'public', false) "
        "FROM lab_read.devices LIMIT 1",
        "SELECT pg_advisory_lock(1) FROM lab_read.devices LIMIT 1",
        "SELECT device_id FROM lab_read.devices -- comentario\nLIMIT 1",
        "SELECT d.device_id FROM lab_read.devices AS d "
        "JOIN lab_read.measurements AS m USING (device_id) LIMIT 1",
        "SELECT position FROM lab_read.devices LIMIT 1",
    ]

    for sql in rejected:
        with pytest.raises(SQLRejected):
            validate_sql(sql)


def test_rejected_sql_preview_is_single_line_escaped_and_bounded() -> None:
    preview = safe_sql_preview("SELECT 1\n" + "x" * 400)

    assert "\\n" in preview
    assert "\n" not in preview
    assert len(preview) < 270


def _readonly_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "ceiot_class6"),
        user=os.getenv("AI_POSTGRES_USER", "ai_readonly"),
        password=os.environ["AI_POSTGRES_PASSWORD"],
        autocommit=True,
    )


def test_readonly_roles_have_only_the_expected_privileges() -> None:
    with _readonly_connection() as connection:
        assert connection.execute("SELECT current_user").fetchone() == (
            "ai_readonly",
        )
        assert connection.execute(
            "SHOW default_transaction_read_only"
        ).fetchone() == ("on",)
        assert connection.execute("SHOW search_path").fetchone() == ("pg_catalog",)

        observed = connection.execute(
            """
            WITH relation_oids AS (
                SELECT
                    max(class.oid) FILTER (
                        WHERE namespace.nspname = 'lab_read'
                          AND class.relname = 'measurements'
                    ) AS lab_measurements,
                    max(class.oid) FILTER (
                        WHERE namespace.nspname = 'lab_read'
                          AND class.relname = 'devices'
                    ) AS lab_devices,
                    max(class.oid) FILTER (
                        WHERE namespace.nspname = 'public'
                          AND class.relname = 'manual_chunks'
                    ) AS manual_chunks,
                    max(class.oid) FILTER (
                        WHERE namespace.nspname = 'public'
                          AND class.relname = 'manual_documents'
                    ) AS manual_documents,
                    max(class.oid) FILTER (
                        WHERE namespace.nspname = 'public'
                          AND class.relname = 'measurements'
                    ) AS measurements
                FROM pg_catalog.pg_class AS class
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = class.relnamespace
            )
            SELECT
                has_schema_privilege(
                    'ai_readonly', 'public', 'USAGE'
                ),
                has_schema_privilege(
                    'ai_readonly', 'public', 'CREATE'
                ),
                has_database_privilege(
                    'ai_readonly', current_database(), 'TEMPORARY'
                ),
                has_schema_privilege(
                    'ai_readonly', 'lab_read', 'USAGE'
                ),
                has_table_privilege(
                    'ai_readonly', lab_measurements, 'SELECT'
                ),
                has_table_privilege(
                    'ai_readonly', lab_devices, 'SELECT'
                ),
                has_table_privilege(
                    'ai_readonly', manual_chunks, 'SELECT'
                ),
                has_table_privilege(
                    'ai_readonly', manual_documents, 'SELECT'
                ),
                has_table_privilege(
                    'ai_readonly', measurements, 'INSERT'
                ),
                has_schema_privilege(
                    'rag_readonly', 'public', 'USAGE'
                ),
                has_schema_privilege(
                    'rag_readonly', 'public', 'CREATE'
                ),
                has_database_privilege(
                    'rag_readonly', current_database(), 'TEMPORARY'
                ),
                has_schema_privilege(
                    'rag_readonly', 'lab_read', 'USAGE'
                ),
                has_table_privilege(
                    'rag_readonly', lab_measurements, 'SELECT'
                ),
                has_table_privilege(
                    'rag_readonly', lab_devices, 'SELECT'
                ),
                has_table_privilege(
                    'rag_readonly', manual_chunks, 'SELECT'
                ),
                has_table_privilege(
                    'rag_readonly', manual_documents, 'SELECT'
                ),
                has_table_privilege(
                    'rag_readonly', measurements, 'INSERT'
                )
            FROM relation_oids
            """
        ).fetchone()
        assert observed == (
            False,
            False,
            False,
            True,
            True,
            True,
            False,
            False,
            False,
            True,
            False,
            False,
            False,
            False,
            False,
            True,
            True,
            False,
        )
