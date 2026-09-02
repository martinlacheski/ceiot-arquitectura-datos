from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from .repository import MeasurementRepository
from .schemas import MeasurementCreate, MeasurementRead
from .service import MeasurementService

router = APIRouter(prefix="/measurements", tags=["measurements"])


def get_service(session: AsyncSession = Depends(get_session)) -> MeasurementService:
    return MeasurementService(MeasurementRepository(session))


@router.get("", response_model=list[MeasurementRead])
async def list_measurements(service: MeasurementService = Depends(get_service)) -> list[MeasurementRead]:
    return [MeasurementRead.model_validate(item) for item in await service.list()]


@router.post("", response_model=MeasurementRead, status_code=status.HTTP_201_CREATED)
async def create_measurement(
    payload: MeasurementCreate, service: MeasurementService = Depends(get_service)
) -> MeasurementRead:
    return MeasurementRead.model_validate(await service.create(payload))
