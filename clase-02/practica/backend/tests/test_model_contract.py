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
