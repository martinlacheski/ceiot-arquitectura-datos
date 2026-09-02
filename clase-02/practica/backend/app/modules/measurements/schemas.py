# pyright: reportMissingImports=false
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MeasurementCreate(BaseModel):
    device_id: UUID
    variable: str = Field(min_length=1, max_length=80)
    value: Decimal
    unit: str = Field(min_length=1, max_length=24)
    recorded_at: datetime


class MeasurementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    device_id: UUID
    variable: str
    value: Decimal
    unit: str
    recorded_at: datetime
    created_at: datetime
