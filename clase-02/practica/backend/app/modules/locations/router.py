from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from .repository import LocationRepository
from .schemas import LocationCreate, LocationRead
from .service import LocationService

router = APIRouter(prefix="/locations", tags=["locations"])


def get_service(session: AsyncSession = Depends(get_session)) -> LocationService:
    return LocationService(LocationRepository(session))


@router.get("", response_model=list[LocationRead])
async def list_locations(service: LocationService = Depends(get_service)) -> list[LocationRead]:
    return [LocationRead.model_validate(item) for item in await service.list()]


@router.post("", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
async def create_location(payload: LocationCreate, service: LocationService = Depends(get_service)) -> LocationRead:
    return LocationRead.model_validate(await service.create(payload))
