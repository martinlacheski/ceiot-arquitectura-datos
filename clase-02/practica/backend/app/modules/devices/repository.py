from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Device
from .schemas import DeviceCreate


class DeviceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Device]:
        return list((await self.session.exec(select(Device).order_by(Device.name))).all())

    async def create(self, payload: DeviceCreate) -> Device:
        entity = Device(**payload.model_dump())
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity
