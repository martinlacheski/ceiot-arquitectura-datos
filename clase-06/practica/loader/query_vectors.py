#!/usr/bin/env python3
"""Compara recuperación semántica pgvector con coincidencia literal ILIKE."""

from __future__ import annotations

import argparse
import os
from typing import Any

from loader.ingest_vectors import postgres_connection
from shared.embeddings import (  # type: ignore[import-not-found]
    MODEL_NAME,
    embedding_model,
    query_text,
    vector_literal,
)
from shared.retrieval import nearest_manual_chunks  # type: ignore[import-not-found]

DEFAULT_QUESTION = "¿Cómo debe recalibrarse el sensor ENV-X después de reemplazar la batería?"


def semantic_search(cursor: Any, embedding: str, top_k: int) -> list[tuple[Any, ...]]:
    """Compatibilidad del CLI sobre la recuperación pgvector compartida."""

    return nearest_manual_chunks(cursor, embedding, top_k)  # type: ignore[return-value]


def literal_search(cursor: Any, question: str, top_k: int) -> list[tuple[Any, ...]]:
    # A propósito se compara la paráfrasis completa: ILIKE no comprende significado.
    cursor.execute(
        """
        SELECT document_id, version, page, section, chunk_index, object_key, content
        FROM manual_chunks
        WHERE content ILIKE '%%' || %s || '%%'
        ORDER BY document_id, version, chunk_index
        LIMIT %s
        """,
        (question, top_k),
    )
    return cursor.fetchall()


def print_results(title: str, rows: list[tuple[Any, ...]], semantic: bool) -> None:
    print(f"\n=== {title} ({len(rows)} resultados) ===")
    if not rows:
        print("Sin coincidencias.")
        return
    for row in rows:
        document_id, version, page, section, chunk_index, object_key, content, *tail = row
        distance = f", distancia_coseno={tail[0]:.6f}" if semantic else ""
        print(
            f"- {document_id} v{version}, página {page}, sección {section!r}, "
            f"chunk {chunk_index}, object_key={object_key}{distance}\n  {content}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    if not args.question.strip():
        raise SystemExit("La pregunta no puede estar vacía")
    if not 1 <= args.top_k <= 4:
        raise SystemExit("--top-k debe estar entre 1 y 4")

    model_name: str = os.environ.get("MODELO_EMBEDDING") or MODEL_NAME
    if model_name != MODEL_NAME:
        raise ValueError(f"Esta práctica fija MODELO_EMBEDDING={MODEL_NAME}")
    print(f"Cargando modelo local {model_name}.")
    model = embedding_model()
    embedding = model.encode(query_text(args.question), normalize_embeddings=True)
    encoded = vector_literal(embedding)

    with postgres_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*), min(embedding_model), max(embedding_model) FROM manual_chunks")
        count, first_model, last_model = cursor.fetchone()
        if count == 0:
            raise RuntimeError("No hay chunks: ejecutá primero ingest_vectors.py")
        if first_model != model_name or last_model != model_name:
            raise RuntimeError("Los chunks no fueron indexados con el modelo de consulta")
        semantic_rows = semantic_search(cursor, encoded, args.top_k)
        literal_rows = literal_search(cursor, args.question, args.top_k)

    print(f"Pregunta para ambas estrategias: {args.question}")
    print_results("Top-k semántico con <=>", semantic_rows, semantic=True)
    print_results("Coincidencia literal con ILIKE", literal_rows, semantic=False)


if __name__ == "__main__":
    main()
