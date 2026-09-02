from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlmodel import Field, SQLModel

UUID_COLUMN = PostgreSQLUUID(as_uuid=True)
TIMESTAMP_COLUMN = DateTime(timezone=True)
UUID_DEFAULT = text("gen_random_uuid()")
TIMESTAMP_DEFAULT = text("now()")


def uuid_primary_key() -> Column[UUID]:
    return Column(UUID_COLUMN, primary_key=True, server_default=UUID_DEFAULT)


def timestamp_column() -> Column[datetime]:
    return Column(TIMESTAMP_COLUMN, nullable=False, server_default=TIMESTAMP_DEFAULT)


class Organization(SQLModel, table=True):
    __tablename__: Any = "organizations"

    id: UUID | None = Field(default=None, sa_column=uuid_primary_key())
    name: str = Field(sa_column=Column(String(120), nullable=False, unique=True))
    created_at: datetime | None = Field(default=None, sa_column=timestamp_column())


class User(SQLModel, table=True):
    __tablename__: Any = "users"

    id: UUID | None = Field(default=None, sa_column=uuid_primary_key())
    email: str = Field(sa_column=Column(String(320), nullable=False, unique=True))
    display_name: str = Field(sa_column=Column(String(120), nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=timestamp_column())


class OrganizationUser(SQLModel, table=True):
    __tablename__: Any = "organization_users"
    __table_args__ = (CheckConstraint("role IN ('owner', 'operator', 'viewer')"),)

    organization_id: UUID = Field(sa_column=Column(UUID_COLUMN, ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True))
    user_id: UUID = Field(sa_column=Column(UUID_COLUMN, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True))
    role: str = Field(default="viewer", sa_column=Column(String(40), nullable=False, server_default=text("'viewer'")))
    created_at: datetime | None = Field(default=None, sa_column=timestamp_column())


class Location(SQLModel, table=True):
    __tablename__: Any = "locations"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="locations_organization_name_key"),
        CheckConstraint("latitude BETWEEN -90 AND 90"),
        CheckConstraint("longitude BETWEEN -180 AND 180"),
        Index("locations_organization_id_idx", "organization_id"),
    )

    id: UUID | None = Field(default=None, sa_column=uuid_primary_key())
    organization_id: UUID = Field(sa_column=Column(UUID_COLUMN, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False))
    name: str = Field(sa_column=Column(String(120), nullable=False))
    description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    latitude: Decimal | None = Field(default=None, sa_column=Column(Numeric(8, 5), nullable=True))
    longitude: Decimal | None = Field(default=None, sa_column=Column(Numeric(8, 5), nullable=True))
    created_at: datetime | None = Field(default=None, sa_column=timestamp_column())


class Device(SQLModel, table=True):
    __tablename__: Any = "devices"
    __table_args__ = (Index("devices_organization_id_idx", "organization_id"),)

    id: UUID | None = Field(default=None, sa_column=uuid_primary_key())
    organization_id: UUID = Field(sa_column=Column(UUID_COLUMN, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False))
    name: str = Field(sa_column=Column(String(120), nullable=False))
    serial_number: str = Field(sa_column=Column(String(120), nullable=False, unique=True))
    model: str | None = Field(default=None, sa_column=Column(String(120), nullable=True))
    installed_at: datetime | None = Field(default=None, sa_column=Column(TIMESTAMP_COLUMN, nullable=True))
    created_at: datetime | None = Field(default=None, sa_column=timestamp_column())


class Measurement(SQLModel, table=True):
    __tablename__: Any = "measurements"
    __table_args__ = (
        CheckConstraint("variable <> ''"),
        CheckConstraint("unit <> ''"),
        Index("measurements_device_recorded_at_idx", "device_id", text("recorded_at DESC")),
    )

    id: UUID | None = Field(default=None, sa_column=uuid_primary_key())
    device_id: UUID = Field(sa_column=Column(UUID_COLUMN, ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False))
    variable: str = Field(sa_column=Column(String(80), nullable=False))
    value: Decimal = Field(sa_column=Column(Numeric(14, 4), nullable=False))
    unit: str = Field(sa_column=Column(String(24), nullable=False))
    recorded_at: datetime = Field(sa_column=Column(TIMESTAMP_COLUMN, nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=timestamp_column())


class DeviceStatusHistory(SQLModel, table=True):
    __tablename__: Any = "device_status_history"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive', 'maintenance')"),
        CheckConstraint("ended_at IS NULL OR ended_at > started_at"),
        Index("device_status_one_current_idx", "device_id", unique=True, postgresql_where=text("ended_at IS NULL")),
    )

    id: UUID | None = Field(default=None, sa_column=uuid_primary_key())
    device_id: UUID = Field(sa_column=Column(UUID_COLUMN, ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False))
    status: str = Field(sa_column=Column(String(30), nullable=False))
    started_at: datetime = Field(sa_column=Column(TIMESTAMP_COLUMN, nullable=False))
    ended_at: datetime | None = Field(default=None, sa_column=Column(TIMESTAMP_COLUMN, nullable=True))


class DeviceLocationHistory(SQLModel, table=True):
    __tablename__: Any = "device_location_history"
    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at > started_at"),
        Index("device_location_one_current_idx", "device_id", unique=True, postgresql_where=text("ended_at IS NULL")),
    )

    id: UUID | None = Field(default=None, sa_column=uuid_primary_key())
    device_id: UUID = Field(sa_column=Column(UUID_COLUMN, ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False))
    location_id: UUID = Field(sa_column=Column(UUID_COLUMN, ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False))
    started_at: datetime = Field(sa_column=Column(TIMESTAMP_COLUMN, nullable=False))
    ended_at: datetime | None = Field(default=None, sa_column=Column(TIMESTAMP_COLUMN, nullable=True))
