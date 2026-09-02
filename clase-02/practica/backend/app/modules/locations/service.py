from app.models import Location
from .repository import LocationRepository
from .schemas import LocationCreate


class LocationService:
    def __init__(self, repository: LocationRepository) -> None:
        self.repository = repository

    async def list(self) -> list[Location]:
        return await self.repository.list()

    async def create(self, payload: LocationCreate) -> Location:
        return await self.repository.create(payload)
