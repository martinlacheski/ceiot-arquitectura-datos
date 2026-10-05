from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest  # type: ignore[import-not-found]

from loader.pdf_document import PageChunk, passage_text  # type: ignore[import-not-found]
from shared.embeddings import EXPECTED_DIMENSION, model_dimension, query_text, vector_literal  # type: ignore[import-not-found]
from shared.retrieval import MAX_COSINE_DISTANCE, nearest_manual_chunks  # type: ignore[import-not-found]


class FakeModel:
    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def get_sentence_embedding_dimension(self) -> int:
        return self.dimension


def test_model_dimension_must_match_vector_1024() -> None:
    assert model_dimension(FakeModel(EXPECTED_DIMENSION)) == 1024

    with pytest.raises(ValueError, match=r"VECTOR\(1024\)"):
        model_dimension(FakeModel(384))


def test_vector_literal_rejects_wrong_dimension() -> None:
    with pytest.raises(ValueError, match="se esperaban 1024"):
        vector_literal([0.1, 0.2])

    rendered = vector_literal([0.0] * EXPECTED_DIMENSION)
    assert rendered.startswith("[") and rendered.endswith("]")
    assert rendered.count(",") == EXPECTED_DIMENSION - 1


def test_bge_m3_uses_no_prefixes_unlike_e5() -> None:
    chunk = PageChunk(
        document_id="upload-0123456789abcdef01234567",
        version=1,
        page=1,
        section="Introducción",
        chunk_index=0,
        content="Texto de ejemplo del fragmento.",
        object_key="documentos/ejemplo.pdf",
    )

    assert passage_text(chunk) == "Introducción. " + chunk.content
    assert not passage_text(chunk).startswith("passage:")
    assert query_text("¿Cómo calibro el sensor?") == "¿Cómo calibro el sensor?"
    assert not query_text("¿Cómo calibro el sensor?").startswith("query:")


class ThresholdCursor:
    def __init__(self, distances: list[float]) -> None:
        self.distances = distances
        self.sql = ""
        self.params: tuple[Any, ...] = ()

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.sql = sql
        self.params = params

    def fetchall(self) -> list[tuple[Any, ...]]:
        threshold, top_k = self.params[-2:]
        return [
            ("doc", 1, 1, "section", index, "manual.pdf", "text", distance)
            for index, distance in enumerate(self.distances)
            if distance <= threshold
        ][:top_k]


def test_retrieval_applies_parameterized_threshold_before_order_and_limit() -> None:
    just_under = MAX_COSINE_DISTANCE - 0.000001
    just_over = MAX_COSINE_DISTANCE + 0.000001
    cursor = ThresholdCursor([just_under, MAX_COSINE_DISTANCE, just_over])

    rows: list[tuple[Any, ...]] = nearest_manual_chunks(  # type: ignore[assignment]
        cursor, "[vector]", 4
    )

    assert [row[-1] for row in rows] == [just_under, MAX_COSINE_DISTANCE]
    normalized_sql = " ".join(cursor.sql.split())
    assert normalized_sql.index("WHERE cosine_distance <= %s") < normalized_sql.index(
        "ORDER BY cosine_distance"
    ) < normalized_sql.index("LIMIT %s")
    assert cursor.params == ("[vector]", MAX_COSINE_DISTANCE, 4)


def test_retrieval_filters_available_indexed_documents_before_top_k() -> None:
    cursor = ThresholdCursor([0.12])

    nearest_manual_chunks(cursor, "[vector]", 2)

    normalized_sql = " ".join(cursor.sql.split())
    assert "JOIN public.manual_documents AS document" in normalized_sql
    assert "document.storage_status = 'available'" in normalized_sql
    assert "document.index_status = 'indexed'" in normalized_sql
    assert normalized_sql.index("document.index_status = 'indexed'") < normalized_sql.index(
        ") AS candidates"
    ) < normalized_sql.index("WHERE cosine_distance <= %s")


def test_selected_document_filter_is_parameterized_inside_candidates_before_top_k() -> None:
    document_id = "upload-0123456789abcdef01234567"
    cursor = ThresholdCursor([])

    rows = nearest_manual_chunks(
        cursor, "[vector]", 3, document_id=document_id
    )

    assert rows == []
    normalized_sql = " ".join(cursor.sql.split())
    assert normalized_sql.index("AND chunk.document_id = %s") < normalized_sql.index(
        ") AS candidates"
    ) < normalized_sql.index("WHERE cosine_distance <= %s") < normalized_sql.index(
        "ORDER BY cosine_distance"
    ) < normalized_sql.index("LIMIT %s")
    assert cursor.params == ("[vector]", document_id, MAX_COSINE_DISTANCE, 3)


def test_selected_document_filter_rejects_noncanonical_id_before_sql() -> None:
    cursor = ThresholdCursor([])

    with pytest.raises(ValueError, match="formato válido"):
        nearest_manual_chunks(cursor, "[vector]", 2, document_id="doc' OR TRUE --")

    assert cursor.sql == ""


@pytest.mark.parametrize("top_k", [0, 5, True, 1.5])
def test_low_level_retrieval_rejects_invalid_top_k_before_sql(top_k: Any) -> None:
    cursor = ThresholdCursor([0.1])

    with pytest.raises(ValueError, match="top_k"):
        nearest_manual_chunks(cursor, "[vector]", top_k)

    assert cursor.sql == ""


@pytest.mark.parametrize(
    "threshold",
    [-0.1, MAX_COSINE_DISTANCE + 0.01, math.inf, math.nan, True],
)
def test_low_level_retrieval_rejects_unsafe_cosine_cutoff_before_sql(
    threshold: Any,
) -> None:
    cursor = ThresholdCursor([0.1])

    with pytest.raises(ValueError, match="corte coseno"):
        nearest_manual_chunks(
            cursor, "[vector]", 4, max_cosine_distance=threshold
        )

    assert cursor.sql == ""


def test_corpus_calibration_keeps_positive_and_rejects_beyond_threshold() -> None:
    below = MAX_COSINE_DISTANCE * 0.6
    near = MAX_COSINE_DISTANCE * 0.9
    above = MAX_COSINE_DISTANCE * 1.2
    cursor = ThresholdCursor([below * 0.5, below, near, above, above * 1.3])

    rows: list[tuple[Any, ...]] = nearest_manual_chunks(  # type: ignore[assignment]
        cursor, "[vector]", 4
    )

    assert [row[-1] for row in rows] == [below * 0.5, below, near]


def test_native_sql_exposes_cosine_and_literal_operators() -> None:
    sql_path = Path(__file__).resolve().parents[1] / "postgres/examples/04-vector.sql"
    sql = sql_path.read_text(encoding="utf-8")

    assert "<=>" in sql
    assert "ILIKE" in sql
    assert "batería" in sql
