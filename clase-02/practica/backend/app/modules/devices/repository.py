from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Device, DeviceLocationHistory, Location, Organization
from .schemas import DeviceCreate, DeviceRead


class LocationNotFoundError(ValueError):
    pass


class LocationOrganizationMismatchError(ValueError):
    pass


class DeviceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[DeviceRead]:
        statement = (
            select(
                Device,
                Organization.name,
                DeviceLocationHistory.location_id,
                Location.name,
            )
            .join(Organization, col(Organization.id) == col(Device.organization_id))
            .outerjoin(
                DeviceLocationHistory,
                and_(
                    col(DeviceLocationHistory.device_id) == col(Device.id),
                    col(DeviceLocationHistory.ended_at).is_(None),
                ),
            )
                .outerjoin(
                    Location,
                    col(Location.id) == col(DeviceLocationHistory.location_id),
                )
            .order_by(Device.name)
        )
        rows = (await self.session.exec(statement)).all()
        return [
            DeviceRead.model_validate(device).model_copy(
                update={
                    "organization_name": organization_name,
                    "current_location_id": location_id,
                    "current_location_name": location_name,
                }
            )
            for device, organization_name, location_id, location_name in rows
        ]

    async def create(self, payload: DeviceCreate) -> DeviceRead:
        device_fields = payload.model_dump(exclude={"location_id"})
        started_at = payload.installed_at or datetime.now(timezone.utc)

        async with self.session.begin():
            location = (
                await self.session.exec(
                    select(Location).where(Location.id == payload.location_id)
                )
            ).one_or_none()
            if location is None:
                raise LocationNotFoundError("La ubicación seleccionada no existe.")
            if location.organization_id != payload.organization_id:
                raise LocationOrganizationMismatchError(
                    "La ubicación seleccionada no pertenece a la organización elegida."
                )
            location_name = location.name

            entity = Device(**device_fields)
            self.session.add(entity)
            await self.session.flush()
            if entity.id is None:
                raise RuntimeError("La base de datos no generó el ID del dispositivo.")
            self.session.add(
                DeviceLocationHistory(
                    device_id=entity.id,
                    location_id=payload.location_id,
                    started_at=started_at,
                )
            )
        await self.session.refresh(entity)
        return DeviceRead.model_validate(entity).model_copy(
            update={
                "current_location_id": payload.location_id,
                "current_location_name": location_name,
            }
        )
