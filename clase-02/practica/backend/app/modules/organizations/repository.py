from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Organization
from .schemas import OrganizationCreate


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Organization]:
        return list((await self.session.exec(select(Organization).order_by(Organization.name))).all())

    async def create(self, payload: OrganizationCreate) -> Organization:
        entity = Organization(name=payload.name)
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity
