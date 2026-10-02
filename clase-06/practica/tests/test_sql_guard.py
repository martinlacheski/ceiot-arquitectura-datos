"""Open Text-to-SQL: the guard only blocks non-read statements; the database enforces the rest."""

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
from shared.sql_query import (  # type: ignore[import-not-found]
    MAX_RESULT_ROWS,
    execute_validated_sql,
)

# Needs a JOIN: public.measurements has no location_id, devices does.
JOIN_AVERAGE_QUERY = """
SELECT AVG(m.value) AS average_co2
FROM measurements AS m
JOIN devices AS d ON d.device_id = m.device_id
WHERE d.location_id = 'LAB-101'
  AND m.variable = 'co2'
  AND m.measured_at >= '2025-05-12T00:00:00Z'
  AND m.measured_at < '2025-05-13T00:00:00Z'
"""


@pytest.mark.parametrize(
    "sql",
    [
        JOIN_AVERAGE_QUERY,
        "WITH recent AS (SELECT * FROM measurements WHERE measured_at >= now() - INTERVAL '1 day') "
        "SELECT variable, count(*) FROM recent GROUP BY variable",
        "SELECT device_id FROM devices WHERE location_id IN (SELECT location_id FROM locations)",
        "SELECT time_bucket('1 hour', measured_at) AS hour, round(avg(value), 2) "
        "FROM measurements GROUP BY 1 ORDER BY 1",
        "SELECT device_id, value, rank() OVER (ORDER BY value DESC) FROM measurements",
        "SELECT a.device_id, ST_Distance(a.position, b.position) FROM devices a, devices b",
        "SELECT 1 UNION SELECT 2",
        "select * from measurements -- comentario",
    ],
)
def test_accepts_any_single_read_only_query(sql: str) -> None:
    validated = validate_sql(sql)

    assert validated.sql.strip()


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM measurements",
        "INSERT INTO locations VALUES ('X', 'x', 'x', NULL)",
        "UPDATE devices SET model = 'x'",
        "DROP TABLE measurements",
        "TRUNCATE measurements",
        "CREATE TABLE x (id int)",
        "ALTER TABLE devices ADD COLUMN x int",
        "SET statement_timeout = 0",
        "COPY measurements TO '/tmp/x'",
        "SELECT 1; DELETE FROM measurements",
        "WITH gone AS (DELETE FROM measurements RETURNING *) SELECT * FROM gone",
        "SELECT * INTO copia FROM measurements",
        "",
    ],
)
def test_rejects_anything_that_is_not_a_single_read(sql: str) -> None:
    with pytest.raises(SQLRejected):
        validate_sql(sql)


def test_rejected_sql_preview_is_single_line_escaped_and_bounded() -> None:
    preview = safe_sql_preview("SELECT 1\n" + "x" * 400)

    assert "\\n" in preview
    assert "\n" not in preview
    assert len(preview) < 270


def test_executes_a_join_over_the_real_tables_as_ai_readonly() -> None:
    result = execute_validated_sql(validate_sql(JOIN_AVERAGE_QUERY))

    assert result.columns == ("average_co2",)
    assert result.rows[0]["average_co2"].quantize(Decimal("0.001")) == Decimal("805.667")


def test_large_results_are_truncated_instead_of_failing() -> None:
    result = execute_validated_sql(
        validate_sql("SELECT generate_series(1, 500) AS n")
    )

    assert len(result.rows) == MAX_RESULT_ROWS
    assert result.truncated is True


def _readonly_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "ceiot_class6"),
        user=os.getenv("AI_POSTGRES_USER", "ai_readonly"),
        password=os.environ["AI_POSTGRES_PASSWORD"],
        autocommit=True,
    )


def test_the_database_itself_blocks_writes_from_ai_readonly() -> None:
    with _readonly_connection() as connection:
        with pytest.raises(psycopg.Error):
            connection.execute(
                "INSERT INTO locations (location_id, name, building, position) "
                "VALUES ('HACK', 'x', 'x', 'POINT(0 0)')"
            )


def test_readonly_roles_have_only_the_expected_privileges() -> None:
    with _readonly_connection() as connection:
        assert connection.execute("SELECT current_user").fetchone() == ("ai_readonly",)
        assert connection.execute("SHOW default_transaction_read_only").fetchone() == ("on",)
        assert connection.execute("SHOW search_path").fetchone() == ("public, pg_catalog",)

        observed = connection.execute(
            """
            SELECT
                has_schema_privilege('ai_readonly', 'public', 'USAGE'),
                has_schema_privilege('ai_readonly', 'public', 'CREATE'),
                has_database_privilege('ai_readonly', current_database(), 'TEMPORARY'),
                has_table_privilege('ai_readonly', 'public.measurements', 'SELECT'),
                has_table_privilege('ai_readonly', 'public.devices', 'SELECT'),
                has_table_privilege('ai_readonly', 'public.locations', 'SELECT'),
                has_table_privilege('ai_readonly', 'public.manual_documents', 'SELECT'),
                has_table_privilege('ai_readonly', 'public.measurements', 'INSERT'),
                has_table_privilege('ai_readonly', 'public.devices', 'UPDATE'),
                has_table_privilege('ai_readonly', 'public.locations', 'DELETE'),
                has_schema_privilege('rag_readonly', 'public', 'USAGE'),
                has_schema_privilege('rag_readonly', 'public', 'CREATE'),
                has_table_privilege('rag_readonly', 'public.manual_chunks', 'SELECT'),
                has_table_privilege('rag_readonly', 'public.measurements', 'SELECT')
            """
        ).fetchone()
        assert observed == (
            True, False, False,
            True, True, True, True,
            False, False, False,
            True, False, True, False,
        )
