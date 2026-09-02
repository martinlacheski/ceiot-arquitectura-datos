from app.models import Organization
from .repository import OrganizationRepository
from .schemas import OrganizationCreate


class OrganizationService:
    def __init__(self, repository: OrganizationRepository) -> None:
        self.repository = repository

    async def list(self) -> list[Organization]:
        return await self.repository.list()

    async def create(self, payload: OrganizationCreate) -> Organization:
        return await self.repository.create(payload)
