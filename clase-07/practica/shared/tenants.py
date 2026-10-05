"""Usuarios simulados y su organización (tenant).

La práctica no tiene login real: la UI elige un usuario simulado y el backend
traduce ese usuario a una organización. El cliente envía sólo ``user_id``;
nunca un ``organization_id`` ni un ``tenant_id``, porque entonces cualquiera
podría pedir los datos de otra organización. En producción esta tabla sería la
identidad autenticada (sesión, token) y no un diccionario.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Tenant:
    """Usuario simulado y la organización a la que pertenece."""

    user_id: str
    organization_id: int
    label: str


_USERS: dict[str, Tenant] = {
    tenant.user_id: tenant
    for tenant in (
        Tenant("ana", 1, "Ana — Organización A"),
        Tenant("bruno", 2, "Bruno — Organización B"),
    )
}


def resolve_user(user_id: object) -> Tenant:
    """Devuelve el tenant del usuario; un usuario desconocido es ``ValueError``."""

    if not isinstance(user_id, str) or user_id not in _USERS:
        raise ValueError("Usuario desconocido.")
    return _USERS[user_id]


def list_users() -> list[dict[str, str]]:
    """Lista para la UI: sólo id y etiqueta, sin datos de la organización."""

    return [{"id": tenant.user_id, "label": tenant.label} for tenant in _USERS.values()]
