#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Proyecta el último estado de AIR-002 desde PostgreSQL hacia Redis."""

from __future__ import annotations

import json
import os
from typing import Any

import psycopg
import redis

from shared.settings import env_int

REDIS_KEY = "iot:last-known:AIR-002"
REDIS_TTL_SECONDS = env_int("REDIS_TTL_SECONDS", 3600, minimum=1)


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Falta la variable requerida {name}")
    return value


def postgres_connection() -> psycopg.Connection[Any]:
    return psycopg.connect(
        host=required_env("POSTGRES_HOST"),
        port=int(required_env("POSTGRES_PORT")),
        user=required_env("POSTGRES_USER"),
        password=required_env("POSTGRES_PASSWORD"),
        dbname=required_env("POSTGRES_DB"),
    )


def latest_state(connection: psycopg.Connection[Any]) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT ON (variable)
                   variable, value::double precision, unit, quality, measured_at
            FROM measurements
            WHERE device_id = 'AIR-002'
            ORDER BY variable, measured_at DESC
            """
        )
        rows = cursor.fetchall()
    if not rows:
        raise RuntimeError("PostgreSQL no contiene historial para AIR-002")
    return {
        "device_id": "AIR-002",
        "source_of_truth": "postgres.measurements",
        "readings": {
            variable: {
                "value": value,
                "unit": unit,
                "quality": quality,
                "measured_at": measured_at.isoformat(),
            }
            for variable, value, unit, quality, measured_at in rows
        },
    }


def seed_redis(state: dict[str, Any]) -> int:
    client = redis.Redis(
        host=required_env("REDIS_HOST"),
        port=int(required_env("REDIS_PORT")),
        password=required_env("REDIS_PASSWORD"),
        decode_responses=True,
    )
    encoded = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    client.set(REDIS_KEY, encoded, ex=REDIS_TTL_SECONDS)
    stored = client.get(REDIS_KEY)
    ttl = client.ttl(REDIS_KEY)
    if stored != encoded or not 0 < ttl <= REDIS_TTL_SECONDS:
        raise RuntimeError("Redis no conservó el estado con un TTL finito")
    return ttl


def main() -> None:
    with postgres_connection() as connection:
        state = latest_state(connection)

    ttl = seed_redis(state)
    print(f"Proyección verificada: {REDIS_KEY}, Redis TTL={ttl}s.")
    print("PostgreSQL conserva el historial; Redis sólo acelera la última lectura.")


if __name__ == "__main__":
    main()
