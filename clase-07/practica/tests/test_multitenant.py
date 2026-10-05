"""Contrato multi-tenant (clase 7): esquema, seed y ausencia de manuales ficticios."""

from __future__ import annotations

import os
import re
from pathlib import Path

import psycopg  # type: ignore[import-not-found]
import pytest  # type: ignore[import-not-found]

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (ROOT / "postgres" / "init" / "02-schema.sql").read_text(encoding="utf-8")
SEED = (ROOT / "postgres" / "seed" / "01-iot.sql").read_text(encoding="utf-8")
COMMENTS = (ROOT / "postgres" / "init" / "06-ai-open-access.sql").read_text(encoding="utf-8")
COMPOSE = (ROOT / "compose.yaml").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")


def _flat(sql: str) -> str:
    return re.sub(r"\s+", " ", sql)


def _table(name: str) -> str:
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {name} \((.*?)\n\);", SCHEMA, flags=re.S
    )
    assert match, f"tabla {name} no encontrada"
    return _flat(match.group(1))


# --- esquema ---------------------------------------------------------------


def test_organizations_table_is_defined() -> None:
    table = _table("organizations")

    assert "organization_id bigint PRIMARY KEY" in table
    assert "name text NOT NULL UNIQUE" in table


@pytest.mark.parametrize("name", ["locations", "devices", "measurements"])
def test_tenant_tables_carry_organization_id(name: str) -> None:
    table = _table(name)

    assert "organization_id bigint NOT NULL REFERENCES organizations (organization_id)" in table


def test_composite_foreign_keys_keep_children_inside_their_tenant() -> None:
    locations = _table("locations")
    devices = _table("devices")
    measurements = _table("measurements")

    assert "UNIQUE (organization_id, location_id)" in locations
    assert "FOREIGN KEY (organization_id, location_id) REFERENCES locations (organization_id, location_id)" in devices
    assert "UNIQUE (organization_id, device_id)" in devices
    assert (
        "FOREIGN KEY (organization_id, depends_on_device_id) "
        "REFERENCES devices (organization_id, device_id)"
    ) in devices
    assert "FOREIGN KEY (organization_id, device_id) REFERENCES devices (organization_id, device_id)" in measurements
    assert "REFERENCES devices (device_id)" not in measurements


def test_devices_have_a_positive_sampling_interval() -> None:
    devices = _table("devices")

    assert "sampling_interval_seconds integer NOT NULL DEFAULT 60" in devices
    assert "CHECK (sampling_interval_seconds > 0)" in devices


def test_measurements_stay_a_hypertable_with_a_tenant_leading_index() -> None:
    flat = _flat(SCHEMA)

    assert "create_hypertable( 'measurements', by_range('measured_at')" in flat
    assert "ON measurements (organization_id, device_id, measured_at DESC)" in flat


def test_catalog_comments_explain_the_tenant_identifier() -> None:
    assert "COMMENT ON TABLE public.organizations" in COMMENTS
    for name in ("locations", "devices", "measurements"):
        assert f"COMMENT ON COLUMN public.{name}.organization_id" in COMMENTS
    assert "tenant" in COMMENTS.split("public.measurements.organization_id", 1)[1].split("\n", 1)[0]


# --- seed ------------------------------------------------------------------


def test_seed_defines_two_organizations_and_no_fictitious_manual() -> None:
    flat = _flat(SEED)

    assert re.search(r"\(\s*1,\s*'Organización A", SEED)
    assert re.search(r"\(\s*2,\s*'Organización B", SEED)
    assert "INSERT INTO manual_documents" not in SEED
    assert "env-x-manual" not in SEED
    assert "manual_count" not in flat
    assert "organization_id" in flat


# --- el manual ficticio ya no existe ---------------------------------------


def test_fictitious_manual_artifacts_are_gone() -> None:
    assert not (ROOT / "data" / "manual-content.json").exists()
    assert not (ROOT / "loader" / "ingest_vectors.py").exists()
    assert "manual-content" not in COMPOSE
    assert "manual-content" not in DOCKERFILE
    assert "COPY data" not in DOCKERFILE


def test_loader_only_projects_state_to_redis() -> None:
    from loader import seed_services  # type: ignore[import-not-found]

    for generator in ("render_pdf", "load_source", "upload_and_verify", "mark_manual_pending"):
        assert not hasattr(seed_services, generator)
    assert "--source" not in DOCKERFILE


# --- base viva -------------------------------------------------------------


def _owner_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "ceiot_class7"),
        user=os.getenv("POSTGRES_USER", "ceiot"),
        password=os.environ["POSTGRES_PASSWORD"],
        autocommit=True,
    )


def test_seeded_database_has_two_organizations_with_data() -> None:
    with _owner_connection() as connection:
        organizations = connection.execute(
            "SELECT organization_id, name FROM public.organizations ORDER BY organization_id"
        ).fetchall()
        per_org = connection.execute(
            """
            SELECT o.organization_id,
                   (SELECT count(*) FROM public.locations l WHERE l.organization_id = o.organization_id),
                   (SELECT count(*) FROM public.devices d WHERE d.organization_id = o.organization_id),
                   (SELECT count(*) FROM public.measurements m WHERE m.organization_id = o.organization_id)
            FROM public.organizations o ORDER BY o.organization_id
            """
        ).fetchall()

    assert [row[0] for row in organizations] == [1, 2]
    assert organizations[0][1].startswith("Organización A")
    assert organizations[1][1].startswith("Organización B")
    (_, a_loc, a_dev, a_meas), (_, b_loc, b_dev, b_meas) = per_org
    assert (a_loc, a_dev) == (3, 4)
    assert (b_loc, b_dev) == (1, 2)
    assert a_meas >= 8 + 96
    assert b_meas > 0


def test_measurement_cannot_point_to_another_tenants_device() -> None:
    with _owner_connection() as connection:
        connection.autocommit = False
        try:
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                connection.execute(
                    """
                    INSERT INTO public.measurements
                        (organization_id, device_id, measured_at, variable, value, unit, quality)
                    VALUES (2, 'AMB-001', now(), 'temperature', 20, 'C', 'GOOD')
                    """
                )
        finally:
            connection.rollback()
