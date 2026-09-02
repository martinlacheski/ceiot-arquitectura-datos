from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Device, DeviceLocationHistory, Location
from app.modules.devices.repository import DeviceRepository
from app.modules.devices.schemas import DeviceCreate


class ScalarResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def one_or_none(self) -> object:
        return self.value

    def all(self) -> list[object]:
        return self.value if isinstance(self.value, list) else []


class FakeSession:
    def __init__(self, location: Location | None, rows: list[object] | None = None) -> None:
        self.location = location
        self.rows = rows
        self.added: list[object] = []
        self.commits = 0
        self.flushes = 0
        self.rolled_back = False

    @asynccontextmanager
    async def begin(self):
        try:
            yield self
        except Exception:
            self.rolled_back = True
            self.added.clear()
            raise
        else:
            self.commits += 1

    async def exec(self, _: object) -> ScalarResult:
        return ScalarResult(self.rows if self.rows is not None else self.location)

    def add(self, entity: object) -> None:
        if isinstance(entity, Device) and entity.id is None:
            entity.id = uuid4()
        self.added.append(entity)

    async def flush(self) -> None:
        self.flushes += 1
        for entity in self.added:
            if isinstance(entity, Device) and entity.created_at is None:
                entity.created_at = datetime.now(timezone.utc)

    async def refresh(self, _: object) -> None:
        return None


def payload(organization_id: UUID, location_id: UUID, installed_at: datetime | None = None) -> DeviceCreate:
    return DeviceCreate(
        organization_id=organization_id,
        location_id=location_id,
        name="Sensor de prueba",
        serial_number="TEST-001",
        installed_at=installed_at,
    )


@pytest.mark.asyncio
async def test_create_persists_device_and_initial_location_history_in_one_transaction() -> None:
    organization_id, location_id = uuid4(), uuid4()
    installed_at = datetime(2025, 1, 1, 12, tzinfo=timezone.utc)
    session = FakeSession(Location(id=location_id, organization_id=organization_id, name="Laboratorio"))

    created = await DeviceRepository(cast(AsyncSession, session)).create(
        payload(organization_id, location_id, installed_at)
    )

    assert created.id is not None
    assert session.commits == 1
    assert session.flushes == 1
    assert len(session.added) == 2
    history = next(item for item in session.added if isinstance(item, DeviceLocationHistory))
    assert history.device_id == created.id
    assert history.location_id == location_id
    assert history.started_at == installed_at


@pytest.mark.asyncio
async def test_create_rejects_a_location_from_another_organization_without_partial_device() -> None:
    organization_id, location_id = uuid4(), uuid4()
    session = FakeSession(Location(id=location_id, organization_id=uuid4(), name="Otra organización"))

    with pytest.raises(ValueError, match="no pertenece"):
        await DeviceRepository(cast(AsyncSession, session)).create(
            payload(organization_id, location_id)
        )

    assert session.added == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_create_rejects_a_missing_location_without_partial_device() -> None:
    session = FakeSession(None)

    with pytest.raises(ValueError, match="no existe"):
        await DeviceRepository(cast(AsyncSession, session)).create(
            payload(uuid4(), uuid4())
        )

    assert session.added == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_list_exposes_the_current_location_from_the_open_history_interval() -> None:
    organization_id, location_id = uuid4(), uuid4()
    device = Device(
        id=uuid4(),
        organization_id=organization_id,
        name="Sensor de prueba",
        serial_number="TEST-002",
        created_at=datetime.now(timezone.utc),
    )
    session = FakeSession(None, [(device, "Laboratorio", location_id, "Planta norte")])

    devices = await DeviceRepository(cast(AsyncSession, session)).list()

    assert devices[0].organization_name == "Laboratorio"
    assert devices[0].current_location_id == location_id
    assert devices[0].current_location_name == "Planta norte"
