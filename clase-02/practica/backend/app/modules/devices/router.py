from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from .repository import (
    DeviceRepository,
    LocationNotFoundError,
    LocationOrganizationMismatchError,
)
from .schemas import DeviceCreate, DeviceRead
from .service import DeviceService

router = APIRouter(prefix="/devices", tags=["devices"])


def get_service(session: AsyncSession = Depends(get_session)) -> DeviceService:
    return DeviceService(DeviceRepository(session))


@router.get("", response_model=list[DeviceRead])
async def list_devices(service: DeviceService = Depends(get_service)) -> list[DeviceRead]:
    return await service.list()


@router.post("", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def create_device(payload: DeviceCreate, service: DeviceService = Depends(get_service)) -> DeviceRead:
    try:
        return await service.create(payload)
    except LocationNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except LocationOrganizationMismatchError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
