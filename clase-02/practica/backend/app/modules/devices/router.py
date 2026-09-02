from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from .repository import DeviceRepository
from .schemas import DeviceCreate, DeviceRead
from .service import DeviceService

router = APIRouter(prefix="/devices", tags=["devices"])


def get_service(session: AsyncSession = Depends(get_session)) -> DeviceService:
    return DeviceService(DeviceRepository(session))


@router.get("", response_model=list[DeviceRead])
async def list_devices(service: DeviceService = Depends(get_service)) -> list[DeviceRead]:
    return [DeviceRead.model_validate(item) for item in await service.list()]


@router.post("", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def create_device(payload: DeviceCreate, service: DeviceService = Depends(get_service)) -> DeviceRead:
    return DeviceRead.model_validate(await service.create(payload))
