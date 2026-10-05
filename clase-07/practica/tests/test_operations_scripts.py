"""Contrato de los laboratorios de operaciones (concurrencia, backup, monitoreo, particionado)."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg  # type: ignore[import-not-found]
import pytest  # type: ignore[import-not-found]

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "postgres" / "examples"
COMPOSE = (ROOT / "compose.yaml").read_text(encoding="utf-8")
INIT = ROOT / "postgres" / "init"


def _service(name: str) -> str:
    block = COMPOSE.split(f"\n  {name}:\n", 1)[1]
    return block.split("\n\n", 1)[0]


def _script(name: str) -> str:
    return (EXAMPLES / name).read_text(encoding="utf-8")


SQL_SCRIPTS = (
    "03-concurrencia-a.sql",
    "03-concurrencia-b.sql",
    "03-concurrencia-observar.sql",
    "04-error-humano.sql",
    "05-monitoreo.sql",
    "06-particionamiento.sql",
)


# --- compose ------------------------------------------------------------------


def test_postgres_preloads_pg_stat_statements() -> None:
    block = _service("postgres")

    assert "shared_preload_libraries=timescaledb,pg_textsearch,pg_stat_statements" in block
    assert "./postgres/init/08-monitoring.sql:/docker-entrypoint-initdb.d/08-monitoring.sql:ro" in block


def test_backups_live_in_a_named_volume_owned_by_postgres() -> None:
    block = _service("postgres")

    assert "postgres_backups:/home/postgres/pgdata/backup" in block
    assert "\n  postgres_backups:" in COMPOSE.split("\nvolumes:\n", 1)[1]


def test_monitoring_init_is_reapplicable() -> None:
    sql = (INIT / "08-monitoring.sql").read_text(encoding="utf-8")

    assert sql.startswith("\\set ON_ERROR_STOP on")
    assert "CREATE EXTENSION IF NOT EXISTS pg_stat_statements" in sql


# --- scripts SQL -----------------------------------------------------------------


@pytest.mark.parametrize("name", SQL_SCRIPTS)
def test_sql_labs_stop_on_first_error(name: str) -> None:
    assert "\\set ON_ERROR_STOP on" in _script(name)[:1500]


def test_backup_script_is_strict_posix_shell() -> None:
    script = _script("04-backup-restore.sh")

    assert script.startswith("#!/bin/sh")
    assert "set -eu" in script
    assert "pg_dump" in script and "-Fc" in script
    assert "timescaledb_pre_restore" in script
    assert "timescaledb_post_restore" in script
    assert "pg_restore" in script
    assert "pg_dumpall --roles-only" in script


@pytest.mark.parametrize(
    ("name", "needles"),
    [
        ("03-concurrencia-a.sql", ("FOR UPDATE", "REPEATABLE READ", "\\prompt", "SET ROLE app_iot")),
        ("03-concurrencia-b.sql", ("FOR UPDATE", "REPEATABLE READ", "\\prompt", "SET ROLE app_iot")),
        ("03-concurrencia-observar.sql", ("pg_stat_activity", "pg_blocking_pids", "pg_locks")),
        ("05-monitoreo.sql", ("pg_stat_statements", "pg_stat_user_tables", "hypertable_size", "EXPLAIN")),
        (
            "06-particionamiento.sql",
            ("PARTITION BY RANGE", "DETACH PARTITION", "show_chunks", "PARTITION BY LIST"),
        ),
    ],
)
def test_labs_contain_their_key_statements(name: str, needles: tuple[str, ...]) -> None:
    text = _script(name)

    for needle in needles:
        assert needle in text, f"{name} debería contener {needle!r}"


def test_concurrency_demo_mentions_deadlock_and_resets_the_value() -> None:
    text = _script("03-concurrencia-a.sql") + _script("03-concurrencia-b.sql")

    assert "deadlock" in text.lower()
    assert "sampling_interval_seconds = 60" in text


def test_partitioning_lab_is_repeatable_and_not_granted_to_ai_readonly() -> None:
    text = _script("06-particionamiento.sql")

    assert "DROP SCHEMA IF EXISTS lab_ops CASCADE" in text
    assert "GRANT " not in text.upper().replace("GRANTED", "")


# --- base viva ---------------------------------------------------------------------


def _owner_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "ceiot_class7"),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        autocommit=True,
    )


def test_live_lab_ops_is_invisible_to_the_ai_role() -> None:
    try:
        connection = _owner_connection()
    except (psycopg.OperationalError, KeyError):
        pytest.skip("PostgreSQL no disponible")
    with connection:
        exists = connection.execute(
            "SELECT count(*) FROM pg_namespace WHERE nspname = 'lab_ops'"
        ).fetchone()[0]
        if not exists:
            pytest.skip("lab_ops todavía no fue creado (ejecutá 06-particionamiento.sql)")
        for role in ("ai_readonly", "rag_readonly", "app_iot"):
            assert not connection.execute(
                "SELECT has_schema_privilege(%s, 'lab_ops', 'USAGE')", (role,)
            ).fetchone()[0]


def test_live_pg_stat_statements_is_available() -> None:
    try:
        connection = _owner_connection()
    except (psycopg.OperationalError, KeyError):
        pytest.skip("PostgreSQL no disponible")
    with connection:
        preload = connection.execute("SHOW shared_preload_libraries").fetchone()[0]
        assert "pg_stat_statements" in preload
        assert connection.execute(
            "SELECT count(*) FROM pg_extension WHERE extname = 'pg_stat_statements'"
        ).fetchone()[0] == 1
