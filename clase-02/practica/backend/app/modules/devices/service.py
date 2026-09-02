from app.models import Device
from .repository import DeviceRepository
from .schemas import DeviceCreate


class DeviceService:
    def __init__(self, repository: DeviceRepository) -> None:
        self.repository = repository

    async def list(self) -> list[Device]:
        return await self.repository.list()

    async def create(self, payload: DeviceCreate) -> Device:
        return await self.repository.create(payload)
