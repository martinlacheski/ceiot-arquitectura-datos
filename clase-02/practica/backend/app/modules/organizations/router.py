from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from .repository import OrganizationRepository
from .schemas import OrganizationCreate, OrganizationRead
from .service import OrganizationService

router = APIRouter(prefix="/organizations", tags=["organizations"])


def get_service(session: AsyncSession = Depends(get_session)) -> OrganizationService:
    return OrganizationService(OrganizationRepository(session))


@router.get("", response_model=list[OrganizationRead])
async def list_organizations(service: OrganizationService = Depends(get_service)) -> list[OrganizationRead]:
    return [OrganizationRead.model_validate(item) for item in await service.list()]


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate, service: OrganizationService = Depends(get_service)
) -> OrganizationRead:
    return OrganizationRead.model_validate(await service.create(payload))
