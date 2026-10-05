"""Identidad de un documento subido, separada por organización (tenant).

El ``document_id`` se deriva del contenido (SHA-256 del PDF) **y** de la
organización. Así, subir dos veces el mismo archivo dentro de una organización
no lo duplica (misma identidad), pero si Ana y Bruno suben el mismo archivo
obtienen dos documentos independientes: cada uno con su propio ``document_id``,
su propia clave en S3 y sus propias filas protegidas por RLS.
"""

from __future__ import annotations

import hashlib


def checked_organization_id(organization_id: object) -> int:
    """Devuelve la organización si es un entero positivo; si no, falla."""

    # bool es subclase de int: True no puede colarse como organización 1.
    if (
        isinstance(organization_id, bool)
        or not isinstance(organization_id, int)
        or organization_id < 1
    ):
        raise ValueError("organization_id debe ser un entero positivo")
    return organization_id


def derive_document_id(organization_id: int, sha256: str) -> str:
    """``upload-`` + 24 hex derivados de (organización, contenido)."""

    organization = checked_organization_id(organization_id)
    digest = hashlib.sha256(f"org-{organization}:{sha256}".encode()).hexdigest()
    return f"upload-{digest[:24]}"


def object_key_for(organization_id: int, document_id: str, sha256: str) -> str:
    """Clave S3 bajo un prefijo por organización: ``uploads/org-<id>/...``."""

    organization = checked_organization_id(organization_id)
    return f"uploads/org-{organization}/{document_id}/v1/{sha256}.pdf"
