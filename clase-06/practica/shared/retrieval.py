"""Consulta compartida de vecinos más cercanos sobre documentos indexados."""

from __future__ import annotations

import math
from typing import Any

from shared.rag_connection import validate_document_id  # type: ignore[import-not-found]

# Umbral didáctico recalibrado empíricamente para BAAI/bge-m3 (ver
# odd/tasks/clase-06-bge-m3.md para las mediciones): las distancias de este
# modelo viven en otra escala que las de E5. Sigue sin ser un clasificador
# semántico universal ni una garantía de relevancia: un resultado filtrado
# no prueba pertinencia y uno descartado no prueba irrelevancia.
MAX_COSINE_DISTANCE = 0.55


def nearest_manual_chunks(
    cursor: Any,
    embedding: str,
    top_k: int,
    *,
    max_cosine_distance: float = MAX_COSINE_DISTANCE,
    document_id: str | None = None,
) -> list[dict[str, Any]] | list[tuple[Any, ...]]:
    """Recupera vecinos disponibles que pasan el corte antes de aplicar top-k."""

    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 4:
        raise ValueError("top_k debe estar entre 1 y 4")
    if (
        isinstance(max_cosine_distance, bool)
        or not isinstance(max_cosine_distance, (int, float))
        or not math.isfinite(max_cosine_distance)
        or not 0 <= max_cosine_distance <= MAX_COSINE_DISTANCE
    ):
        raise ValueError(
            f"El corte coseno debe estar entre 0 y {MAX_COSINE_DISTANCE}"
        )

    if document_id is None:
        cursor.execute(
            """
            SELECT document_id, version, page, section, chunk_index, object_key,
                   content, cosine_distance
            FROM (
                SELECT chunk.document_id, chunk.version, chunk.page, chunk.section,
                       chunk.chunk_index, chunk.object_key, chunk.content,
                       chunk.embedding <=> %s::vector AS cosine_distance
                FROM public.manual_chunks AS chunk
                JOIN public.manual_documents AS document
                  ON document.document_id = chunk.document_id
                 AND document.version = chunk.version
                 AND document.object_key = chunk.object_key
                WHERE document.storage_status = 'available'
                  AND document.index_status = 'indexed'
            ) AS candidates
            WHERE cosine_distance <= %s
            ORDER BY cosine_distance
            LIMIT %s
            """,
            (embedding, max_cosine_distance, top_k),
        )
    else:
        selected_id = validate_document_id(document_id)
        cursor.execute(
            """
            SELECT document_id, version, page, section, chunk_index, object_key,
                   content, cosine_distance
            FROM (
                SELECT chunk.document_id, chunk.version, chunk.page, chunk.section,
                       chunk.chunk_index, chunk.object_key, chunk.content,
                       chunk.embedding <=> %s::vector AS cosine_distance
                FROM public.manual_chunks AS chunk
                JOIN public.manual_documents AS document
                  ON document.document_id = chunk.document_id
                 AND document.version = chunk.version
                 AND document.object_key = chunk.object_key
                WHERE document.storage_status = 'available'
                  AND document.index_status = 'indexed'
                  AND chunk.document_id = %s
            ) AS candidates
            WHERE cosine_distance <= %s
            ORDER BY cosine_distance
            LIMIT %s
            """,
            (embedding, selected_id, max_cosine_distance, top_k),
        )
    return cursor.fetchall()
