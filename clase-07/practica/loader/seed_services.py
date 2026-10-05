#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Proyecta el último estado de cada equipo desde PostgreSQL hacia Redis.

Cada organización (tenant) tiene su propio espacio de nombres de claves:
``iot:org-<organization_id>:last-known:<device_id>``. Un usuario de Redis
(ACL) por organización sólo puede leer su prefijo (ver ``compose.yaml``).

Este proceso es el lote de proyección y corre como administrador (``ceiot`` en
PostgreSQL, que ignora RLS, y el usuario ``default`` de Redis): necesita ver
todas las organizaciones para publicar cada estado en el namespace correcto.
Los consumidores por tenant, en cambio, nunca usan estas credenciales.
"""

from __future__ import annotations

import json
import os
from typing import Any

import psycopg
import redis

from shared.document_identity import checked_organization_id
from shared.settings import env_int

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


def redis_key(organization_id: int, device_id: str) -> str:
    """Clave con namespace por organización: ``iot:org-1:last-known:AIR-002``."""

    return f"iot:org-{checked_organization_id(organization_id)}:last-known:{device_id}"


def latest_states(
    connection: psycopg.Connection[Any],
) -> dict[tuple[int, str], dict[str, Any]]:
    """Último valor de cada variable de cada equipo, agrupado por (organización, equipo)."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT ON (organization_id, device_id, variable)
                   organization_id, device_id, variable,
                   value::double precision, unit, quality, measured_at
            FROM measurements
            ORDER BY organization_id, device_id, variable, measured_at DESC
            """
        )
        rows = cursor.fetchall()
    if not rows:
        raise RuntimeError("PostgreSQL no contiene historial de mediciones")
    states: dict[tuple[int, str], dict[str, Any]] = {}
    for organization_id, device_id, variable, value, unit, quality, measured_at in rows:
        state = states.setdefault(
            (organization_id, device_id),
            {
                "device_id": device_id,
                "organization_id": organization_id,
                "source_of_truth": "postgres.measurements",
                "readings": {},
            },
        )
        state["readings"][variable] = {
            "value": value,
            "unit": unit,
            "quality": quality,
            "measured_at": measured_at.isoformat(),
        }
    return states


def seed_redis(states: dict[tuple[int, str], dict[str, Any]]) -> dict[str, int]:
    """Publica cada estado en el namespace de su organización; devuelve clave -> TTL."""

    client = redis.Redis(
        host=required_env("REDIS_HOST"),
        port=int(required_env("REDIS_PORT")),
        password=required_env("REDIS_PASSWORD"),
        decode_responses=True,
    )
    ttls: dict[str, int] = {}
    for (organization_id, device_id), state in sorted(states.items()):
        key = redis_key(organization_id, device_id)
        encoded = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        client.set(key, encoded, ex=REDIS_TTL_SECONDS)
        stored = client.get(key)
        ttl = client.ttl(key)
        if stored != encoded or not 0 < ttl <= REDIS_TTL_SECONDS:
            raise RuntimeError("Redis no conservó el estado con un TTL finito")
        ttls[key] = ttl
    return ttls


def main() -> None:
    with postgres_connection() as connection:
        states = latest_states(connection)

    ttls = seed_redis(states)
    for key, ttl in ttls.items():
        print(f"Proyección verificada: {key}, Redis TTL={ttl}s.")
    print("PostgreSQL conserva el historial; Redis sólo acelera la última lectura.")


if __name__ == "__main__":
    main()
