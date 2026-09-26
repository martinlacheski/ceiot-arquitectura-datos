"""Configuración y helpers compartidos del modelo E5 local."""

from __future__ import annotations

import os
from collections.abc import Iterable
from functools import lru_cache
from typing import Any

from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

MODEL_NAME = "intfloat/multilingual-e5-small"
EXPECTED_DIMENSION = 384


def model_dimension(model: Any) -> int:
    dimension = model.get_sentence_embedding_dimension()
    if dimension != EXPECTED_DIMENSION:
        raise ValueError(
            f"El modelo produce dimensión {dimension}; "
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
    return f"query: {question.strip()}"


@lru_cache(maxsize=1)
def embedding_model() -> SentenceTransformer:
    """Carga una única instancia CPU del modelo fijado para todo el proceso."""

    model_name = os.getenv("MODELO_EMBEDDING", MODEL_NAME)
    if model_name != MODEL_NAME:
        raise RuntimeError(f"Esta práctica fija MODELO_EMBEDDING={MODEL_NAME}")
    model = SentenceTransformer(model_name, device="cpu")
    model_dimension(model)
    return model
