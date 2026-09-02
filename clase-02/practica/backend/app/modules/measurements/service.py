from app.models import Measurement
from .repository import MeasurementRepository
from .schemas import MeasurementCreate


class MeasurementService:
    def __init__(self, repository: MeasurementRepository) -> None:
        self.repository = repository

    async def list(self) -> list[Measurement]:
        return await self.repository.list()

    async def create(self, payload: MeasurementCreate) -> Measurement:
        return await self.repository.create(payload)
