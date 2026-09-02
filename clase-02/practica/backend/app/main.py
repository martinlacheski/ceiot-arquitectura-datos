from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import get_settings
from .database import engine
from .modules.devices.router import router as devices_router
from .modules.locations.router import router as locations_router
from .modules.measurements.router import router as measurements_router
from .modules.organizations.router import router as organizations_router

API_PREFIX = "/api"
settings = get_settings()
app = FastAPI(
    title="Clase 2 IoT data model API",
    version="1.0.0",
    docs_url=f"{API_PREFIX}/docs",
    openapi_url=f"{API_PREFIX}/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(organizations_router, prefix=API_PREFIX)
app.include_router(locations_router, prefix=API_PREFIX)
app.include_router(devices_router, prefix=API_PREFIX)
app.include_router(measurements_router, prefix=API_PREFIX)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_: Request, __: IntegrityError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": "La operación viola una restricción del modelo."})


@app.get("/health")
async def health() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.execute(select(1))
    return {"status": "ok", "database": "connected"}
