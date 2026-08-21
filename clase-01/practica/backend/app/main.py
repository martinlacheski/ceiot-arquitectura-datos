from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field
from psycopg import OperationalError

from app.database import get_connection


app = FastAPI(title="Sensor Measurements API")


class MeasurementCreate(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    timestamp: datetime
    temperature: float
    humidity: float
    pressure: float | None = None


class Measurement(MeasurementCreate):
    id: int
    created_at: datetime


@app.get("/health")
def health() -> dict[str, str]:
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1")
    except OperationalError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from error
    return {"status": "ok", "database": "connected"}


@app.post(
    "/measurements",
    response_model=Measurement,
    status_code=status.HTTP_201_CREATED,
)
def create_measurement(measurement: MeasurementCreate) -> dict:
    with get_connection() as connection:
        result = connection.execute(
            """
            INSERT INTO measurements
                (device_id, timestamp, temperature, humidity, pressure)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, device_id, timestamp, temperature, humidity,
                      pressure, created_at
            """,
            (
                measurement.device_id,
                measurement.timestamp,
                measurement.temperature,
                measurement.humidity,
                measurement.pressure,
            ),
        ).fetchone()
    return result


@app.get("/measurements", response_model=list[Measurement])
def list_measurements(
    device_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict]:
    query = """
        SELECT id, device_id, timestamp, temperature, humidity,
               pressure, created_at
        FROM measurements
    """
    parameters: tuple = ()
    if device_id is not None:
        query += " WHERE device_id = %s"
        parameters = (device_id,)
    query += " ORDER BY timestamp DESC, id DESC LIMIT %s"
    parameters += (limit,)

    with get_connection() as connection:
        return connection.execute(query, parameters).fetchall()


@app.get("/measurements/latest", response_model=Measurement)
def latest_measurement(device_id: str | None = None) -> dict:
    query = """
        SELECT id, device_id, timestamp, temperature, humidity,
               pressure, created_at
        FROM measurements
    """
    parameters: tuple = ()
    if device_id is not None:
        query += " WHERE device_id = %s"
        parameters = (device_id,)
    query += " ORDER BY timestamp DESC, id DESC LIMIT 1"

    with get_connection() as connection:
        result = connection.execute(query, parameters).fetchone()
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No measurements found",
        )
    return result
