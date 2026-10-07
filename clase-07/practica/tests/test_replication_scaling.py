"""Contrato de los laboratorios de replicación y escalabilidad (slides 56-68)."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg  # type: ignore[import-not-found]
import pytest  # type: ignore[import-not-found]

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "compose.yaml").read_text(encoding="utf-8")
ENV_EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
INIT = ROOT / "postgres" / "init"
SQL_EXAMPLES = ROOT / "postgres" / "examples"
SHELL_EXAMPLES = ROOT / "examples"


def _service(name: str) -> str:
    block = COMPOSE.split(f"\n  {name}:\n", 1)[1]
    return block.split("\n\n", 1)[0]


# --- compose: primario ----------------------------------------------------------


def test_primary_mounts_hba_file_with_a_replication_rule() -> None:
    block = _service("postgres")
    hba = (ROOT / "postgres" / "pg_hba.conf").read_text(encoding="utf-8")

    assert "hba_file=/lab/pg_hba.conf" in block
    assert "./postgres/pg_hba.conf:/lab/pg_hba.conf:ro" in block
    assert "host    replication     replicator" in hba
    rule = next(line for line in hba.splitlines() if line.startswith("host    replication     replicator"))
    assert rule.split()[-1] == "scram-sha-256"
    # Se conservan las reglas que ya tenía el volumen: los scripts por socket local siguen sin contraseña.
    assert "local   all             all                                     trust" in hba
    assert hba.rstrip().splitlines()[-1].split() == ["host", "all", "all", "all", "scram-sha-256"]


def test_primary_limits_slot_retention_and_mounts_replication_init() -> None:
    block = _service("postgres")

    assert "max_slot_wal_keep_size=1GB" in block
    assert "./postgres/init/09-replication.sql:/docker-entrypoint-initdb.d/09-replication.sql:ro" in block


def test_primary_has_configurable_cpu_and_memory_limits() -> None:
    block = _service("postgres")

    assert 'cpus: "${POSTGRES_CPUS:-2}"' in block
    assert "mem_limit: ${POSTGRES_MEM_LIMIT:-4g}" in block
    # La réplica usa el mismo tope: la comparación de lecturas entre nodos es justa.
    replica = _service("postgres-replica")
    assert 'cpus: "${POSTGRES_CPUS:-2}"' in replica


# --- compose: réplica -----------------------------------------------------------


def test_replica_is_an_opt_in_profile_with_its_own_volume() -> None:
    block = _service("postgres-replica")

    assert "profiles:\n      - replica" in block
    assert "postgres_replica_data:/home/postgres/pgdata/data" in block
    assert "\n  postgres_replica_data:" in COMPOSE.split("\nvolumes:\n", 1)[1]
    assert "127.0.0.1:${POSTGRES_REPLICA_PORT:-5438}:5432" in block
    assert "image: timescale/timescaledb-ha:pg17.11-ts2.30.1" in block


def test_replica_bootstraps_with_pg_basebackup_and_a_slot() -> None:
    block = _service("postgres-replica")

    assert "pg_basebackup" in block
    assert "-R" in block and "-C -S replica_1" in block
    assert "PG_VERSION" in block  # sólo clona si el volumen está vacío
    assert "pg_drop_replication_slot" in block  # re-ejecutable con un slot huérfano
    assert "hot_standby=on" in block
    assert "condition: service_healthy" in block


def test_replica_preloads_the_same_libraries_as_the_primary() -> None:
    primary = _service("postgres")
    replica = _service("postgres-replica")
    preload = "shared_preload_libraries=timescaledb,pg_textsearch,pg_stat_statements"

    assert preload in primary and preload in replica


def test_replica_healthcheck_requires_recovery_mode() -> None:
    block = _service("postgres-replica")

    assert "pg_is_in_recovery()" in block
    assert "pg_isready" in block


def test_env_example_documents_new_variables() -> None:
    for name in ("POSTGRES_REPLICA_PORT=", "POSTGRES_CPUS=", "POSTGRES_MEM_LIMIT="):
        assert name in ENV_EXAMPLE


# --- init -------------------------------------------------------------------------


def test_replication_init_creates_a_replication_role_and_is_reapplicable() -> None:
    sql = (INIT / "09-replication.sql").read_text(encoding="utf-8")

    assert sql.startswith("\\set ON_ERROR_STOP on")
    assert "REPLICATION" in sql and "LOGIN" in sql
    assert "replicator" in sql
    assert "pg_roles" in sql  # CREATE si falta, ALTER si ya existe
    assert "ALTER ROLE replicator" in sql


# --- scripts ----------------------------------------------------------------------


@pytest.mark.parametrize("name", ("07-replicacion.sql", "07-replicacion-replica.sql"))
def test_replication_sql_has_no_psql_meta_commands(name: str) -> None:
    text = (SQL_EXAMPLES / name).read_text(encoding="utf-8")

    assert not [line for line in text.splitlines() if line.lstrip().startswith("\\")]


@pytest.mark.parametrize(
    ("path", "needles"),
    [
        (
            SQL_EXAMPLES / "07-replicacion.sql",
            ("pg_stat_replication", "pg_replication_slots", "replay_lag", "pg_wal_lsn_diff", "pg_current_wal_lsn"),
        ),
        (
            SQL_EXAMPLES / "07-replicacion-replica.sql",
            ("pg_is_in_recovery()", "pg_last_wal_replay_lsn()", "pg_policies", "read-only"),
        ),
        (
            SHELL_EXAMPLES / "07-replicacion.sh",
            ("pg_stat_replication", "docker compose", "pause", "unpause", "04-backup-restore.sh", "recuperar"),
        ),
        (
            SHELL_EXAMPLES / "07-failover.sh",
            ("pg_promote", "pg_is_in_recovery", "postgres_replica_data", "pg_drop_replication_slot", "reset"),
        ),
        (
            SHELL_EXAMPLES / "08-escalabilidad.sh",
            ("pgbench", "-S", "POSTGRES_CPUS", "postgres-replica", "clase 8"),
        ),
    ],
)
def test_labs_contain_their_key_statements(path: Path, needles: tuple[str, ...]) -> None:
    text = path.read_text(encoding="utf-8")

    for needle in needles:
        assert needle in text, f"{path.name} debería contener {needle!r}"


@pytest.mark.parametrize("name", ("07-replicacion.sh", "07-failover.sh", "08-escalabilidad.sh"))
def test_shell_labs_are_strict_posix_shell(name: str) -> None:
    script = (SHELL_EXAMPLES / name).read_text(encoding="utf-8")

    assert script.startswith("#!/bin/sh")
    assert "set -eu" in script


def test_failover_never_touches_the_primary_volume() -> None:
    script = (SHELL_EXAMPLES / "07-failover.sh").read_text(encoding="utf-8")

    assert "volume rm" in script
    assert "postgres_data" not in script.replace("postgres_replica_data", "")
    assert "down -v" not in script


# --- base viva --------------------------------------------------------------------


def _connect(host: str) -> psycopg.Connection:
    return psycopg.connect(
        host=host,
        port=5432,
        dbname=os.getenv("POSTGRES_DB", "ceiot_class7"),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        autocommit=True,
        connect_timeout=3,
    )


def test_live_replicator_role_has_replication_but_no_superuser() -> None:
    try:
        connection = _connect(os.getenv("POSTGRES_HOST", "postgres"))
    except (psycopg.OperationalError, KeyError):
        pytest.skip("PostgreSQL no disponible")
    with connection:
        row = connection.execute(
            "SELECT rolreplication, rolsuper, rolcanlogin FROM pg_roles WHERE rolname = 'replicator'"
        ).fetchone()
    if row is None:
        pytest.skip("replicator todavía no existe (aplicá 09-replication.sql)")
    assert row == (True, False, True)


def test_live_replica_is_in_recovery_and_rejects_writes() -> None:
    try:
        connection = _connect("postgres-replica")
    except (psycopg.OperationalError, KeyError):
        pytest.skip("réplica no disponible (docker compose --profile replica up -d --wait)")
    with connection:
        if not connection.execute("SELECT pg_is_in_recovery()").fetchone()[0]:
            pytest.skip("la réplica fue promovida (07-failover.sh reset la restaura)")
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            connection.execute("CREATE TABLE should_fail (id int)")
