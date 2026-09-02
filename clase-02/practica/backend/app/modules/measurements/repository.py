from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Measurement
from .schemas import MeasurementCreate


class MeasurementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Measurement]:
        statement = select(Measurement).order_by(col(Measurement.recorded_at).desc())
        return list((await self.session.exec(statement)).all())

    async def create(self, payload: MeasurementCreate) -> Measurement:
        entity = Measurement(**payload.model_dump())
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity
