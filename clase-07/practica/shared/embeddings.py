"""Configuración y helpers compartidos del modelo de embeddings local."""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from typing import Any

from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

from shared.settings import env_int, env_str  # type: ignore[import-not-found]

# Configurable, pero la tabla (VECTOR(1024)), el corte coseno y el uso sin
# prefijos están calibrados para BAAI/bge-m3: otro modelo requiere adaptarlos.
MODEL_NAME = env_str("MODELO_EMBEDDING", "BAAI/bge-m3")
EXPECTED_DIMENSION = 1024

# Lote de embeddings (medido en el uploader, 2 CPU, bge-m3): con 4 el pico de
# memoria queda plano (~3,2 GiB) aunque crezca el documento; con 32 sube a
# ~3,9 GiB, demasiado cerca del mem_limit de 4g.
EMBEDDING_BATCH_SIZE = env_int("EMBEDDING_BATCH_SIZE", 4, minimum=1, maximum=256)


def model_dimension(model: Any) -> int:
    dimension = model.get_sentence_embedding_dimension()
    if dimension != EXPECTED_DIMENSION:
        raise ValueError(
            f"El modelo {MODEL_NAME} produce dimensión {dimension}; "
            f"la tabla exige VECTOR({EXPECTED_DIMENSION})"
        )
    return dimension


def vector_literal(values: Iterable[float]) -> str:
    vector = [float(value) for value in values]
    if len(vector) != EXPECTED_DIMENSION:
        raise ValueError(
            f"El vector tiene {len(vector)} componentes; "
            f"se esperaban {EXPECTED_DIMENSION}"
        )
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def query_text(question: str) -> str:
    """bge-m3 no usa prefijos E5: el texto de consulta se envía tal cual."""

    return question.strip()


@lru_cache(maxsize=1)
def embedding_model() -> SentenceTransformer:
    """Carga una única instancia CPU del modelo configurado para todo el proceso."""

    model = SentenceTransformer(MODEL_NAME, device="cpu")
    model_dimension(model)
    return model
