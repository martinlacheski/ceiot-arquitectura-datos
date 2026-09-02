from collections import Counter
from pathlib import Path
import re

from sqlalchemy import CheckConstraint, DefaultClause, Text
from sqlmodel import SQLModel

from app.models import (
    Device,
    DeviceLocationHistory,
    DeviceStatusHistory,
    Location,
    Measurement,
    Organization,
    OrganizationUser,
    User,
)


def test_the_eight_agreed_tables_are_registered() -> None:
    assert set(SQLModel.metadata.tables) == {
        "organizations", "users", "organization_users", "locations", "devices",
        "measurements", "device_status_history", "device_location_history",
    }


def test_measurement_is_owned_by_a_device_without_a_sensor_entity() -> None:
    assert "device_id" in Measurement.model_fields
    assert "organization_id" in Device.model_fields
    assert "Sensor" not in {model.__name__ for model in (Organization, User, Location, Device, Measurement)}


def test_history_models_keep_open_interval_constraints() -> None:
    assert any(
        "ended_at IS NULL" in str(rule.sqltext)
        for rule in SQLModel.metadata.tables["device_status_history"].constraints
        if isinstance(rule, CheckConstraint)
    )
    assert any(
        "ended_at IS NULL" in str(rule.sqltext)
        for rule in SQLModel.metadata.tables["device_location_history"].constraints
        if isinstance(rule, CheckConstraint)
    )


def test_seed_data_has_a_deterministic_paginated_iot_shape() -> None:
    seed = (Path(__file__).resolve().parents[2] / "database/sql/02-seed.sql").read_text()

    def rows_for(table: str) -> str:
        match = re.search(
            rf"INSERT INTO {table} .*? VALUES\n(?P<rows>.*?);",
            seed,
            flags=re.DOTALL,
        )
        assert match, f"missing INSERT for {table}"
        return match.group("rows")

    def count_rows(table: str) -> int:
        return len(re.findall(r"^\('[0-9a-f-]{36}'", rows_for(table), flags=re.MULTILINE))

    device_ids = (
        "44444444-4444-4444-4444-444444444444",
        "45454545-4545-4545-4545-454545454545",
        "46464646-4646-4646-4646-464646464646",
        "77777777-7777-7777-7777-777777777777",
        "78787878-7878-7878-7878-787878787878",
        "79797979-7979-7979-7979-797979797979",
    )
    measurement_device_ids = re.findall(
        r"^\('b[0-9a-f-]{35}', '([0-9a-f-]{36})'", rows_for("measurements"), flags=re.MULTILINE
    )
    device_organizations = dict(re.findall(
        r"^\('([0-9a-f-]{36})', '([0-9a-f-]{36})'", rows_for("devices"), flags=re.MULTILINE
    ))
    location_organizations = dict(re.findall(
        r"^\('([0-9a-f-]{36})', '([0-9a-f-]{36})'", rows_for("locations"), flags=re.MULTILINE
    ))
    location_history = dict(re.findall(
        r"^\('c[0-9a-f-]{35}', '([0-9a-f-]{36})', '([0-9a-f-]{36})'", rows_for("device_location_history"), flags=re.MULTILINE
    ))
    status_history_device_ids = re.findall(
        r"^\('a[0-9a-f-]{35}', '([0-9a-f-]{36})'", rows_for("device_status_history"), flags=re.MULTILINE
    )

    assert count_rows("organizations") == 2
    assert count_rows("locations") == 4
    assert count_rows("devices") == 6
    assert count_rows("device_status_history") == 6
    assert count_rows("device_location_history") == 6
    assert count_rows("measurements") == 72
    assert Counter(measurement_device_ids) == Counter({device_id: 12 for device_id in device_ids})
    assert set(status_history_device_ids) == set(device_ids)
    assert set(location_history) == set(device_ids)
    assert all(device_organizations[device_id] == location_organizations[location_id] for device_id, location_id in location_history.items())
    assert all(
        row.rstrip(",").endswith("NULL)")
        for row in rows_for("device_location_history").splitlines()
        if row.startswith("(")
    )
    assert len(set(re.findall(r"(2024-01-\d{2})T\d{2}:\d{2}:\d{2}Z", rows_for("measurements")))) >= 14
    assert seed.count("ON CONFLICT") == 8
    assert "now()" not in seed


def test_models_match_postgres_defaults_types_foreign_keys_and_indexes() -> None:
    tables = SQLModel.metadata.tables

    for table in tables.values():
        if "id" in table.c:
            server_default = table.c.id.server_default
            assert isinstance(server_default, DefaultClause)
            assert "gen_random_uuid" in str(server_default.arg)
        for column in table.columns:
            if column.name.endswith("_at"):
                assert getattr(column.type, "timezone", False) is True
        for foreign_key in table.foreign_keys:
            assert foreign_key.ondelete in {"CASCADE", "RESTRICT"}

    assert isinstance(tables["locations"].c.description.type, Text)
    role_default = tables["organization_users"].c.role.server_default
    assert isinstance(role_default, DefaultClause)
    assert str(role_default.arg) == "'viewer'"
    assert "devices_organization_id_idx" in {index.name for index in tables["devices"].indexes}
    assert any(
        "role IN" in str(constraint.sqltext)
        for constraint in tables["organization_users"].constraints
        if isinstance(constraint, CheckConstraint)
    )
