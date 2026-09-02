from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Location
from .schemas import LocationCreate


class LocationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Location]:
        return list((await self.session.exec(select(Location).order_by(Location.name))).all())

    async def create(self, payload: LocationCreate) -> Location:
        entity = Location(**payload.model_dump())
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity
