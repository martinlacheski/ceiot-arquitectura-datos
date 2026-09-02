from .repository import DeviceRepository
from .schemas import DeviceCreate, DeviceRead


class DeviceService:
    def __init__(self, repository: DeviceRepository) -> None:
        self.repository = repository

    async def list(self) -> list[DeviceRead]:
        return await self.repository.list()

    async def create(self, payload: DeviceCreate) -> DeviceRead:
        return await self.repository.create(payload)
