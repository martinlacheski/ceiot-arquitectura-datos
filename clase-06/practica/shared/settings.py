"""Lectura y validación de configuración desde variables de entorno.

Un valor vacío cuenta como «no definido» (igual que `${VAR:-default}` en Compose).
Un valor inválido falla de inmediato con un mensaje que nombra la variable.
"""

from __future__ import annotations

import math
import os


def _raw(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def env_str(name: str, default: str) -> str:
    return _raw(name) or default


def env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = _raw(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(
            f"La variable de entorno {name}={raw!r} no es un entero válido."
        ) from None
    if (minimum is not None and value < minimum) or (
        maximum is not None and value > maximum
    ):
        raise ValueError(
            f"La variable de entorno {name}={value} debe estar entre "
            f"{minimum if minimum is not None else '-∞'} y "
            f"{maximum if maximum is not None else '∞'}."
        )
    return value


def env_float(
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    raw = _raw(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(
            f"La variable de entorno {name}={raw!r} no es un número válido."
        ) from None
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(
            f"La variable de entorno {name}={raw!r} debe ser un número finito "
            f"entre {minimum} y {maximum}."
        )
    return value
