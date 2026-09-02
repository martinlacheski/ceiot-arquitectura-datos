# pyright: reportMissingImports=false
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeviceCreate(BaseModel):
    organization_id: UUID
    location_id: UUID
    name: str = Field(min_length=1, max_length=120)
    serial_number: str = Field(min_length=1, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    installed_at: datetime | None = None


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    serial_number: str
    model: str | None
    installed_at: datetime | None
    created_at: datetime
    organization_name: str | None = None
    current_location_id: UUID | None = None
    current_location_name: str | None = None
