from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest  # type: ignore[import-not-found]

from loader.ingest_vectors import (  # type: ignore[import-not-found]
    chunks_from_page_texts,
    passage_text,
    validate_object_provenance,
)
from shared.e5 import EXPECTED_DIMENSION, model_dimension, query_text, vector_literal  # type: ignore[import-not-found]
from shared.retrieval import MAX_COSINE_DISTANCE, nearest_manual_chunks  # type: ignore[import-not-found]


PAGE_TEXTS = [
    """Manual de calibración AirQuality-Pro
Documento air-quality-pro-manual · versión 1
Preparación y condiciones
Ubicá el equipo sobre una mesa estable y mantené condiciones ambientales controladas durante quince minutos completos.
Ajuste de referencia
Conectá el patrón de referencia y aplicá un único ajuste cuando la diferencia de CO2 supere el límite.
Proveniencia: manual-content.json · versión 1 · página 1/2
""",
    """Manual de calibración AirQuality-Pro
Documento air-quality-pro-manual · versión 1
Comprobación
Retirá el patrón y confirmá que tres lecturas consecutivas permanezcan cercanas antes de aceptar la calibración.
Recuperación segura
Si falla la comprobación reiniciá desde las condiciones iniciales y conservá el historial en PostgreSQL siempre.
Proveniencia: manual-content.json · versión 1 · página 2/2
""",
]


def test_chunking_preserves_four_section_provenance_records() -> None:
    chunks = chunks_from_page_texts(
        PAGE_TEXTS,
        document_id="air-quality-pro-manual",
        version=1,
        object_key="manuales/air-quality-pro/v1/manual.pdf",
    )

    assert len(chunks) == 4
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2, 3]
    assert [chunk.page for chunk in chunks] == [1, 1, 2, 2]
    assert [chunk.section for chunk in chunks] == [
        "Preparación y condiciones",
        "Ajuste de referencia",
        "Comprobación",
        "Recuperación segura",
    ]
    assert {chunk.document_id for chunk in chunks} == {"air-quality-pro-manual"}
    assert {chunk.version for chunk in chunks} == {1}
    assert {chunk.object_key for chunk in chunks} == {
        "manuales/air-quality-pro/v1/manual.pdf"
    }
    assert all("Proveniencia:" not in chunk.content for chunk in chunks)


def test_chunking_rejects_missing_section_instead_of_inventing_content() -> None:
    broken_pages = [PAGE_TEXTS[0].replace("Ajuste de referencia", ""), PAGE_TEXTS[1]]

    with pytest.raises(ValueError, match="No se encontró la sección"):
        chunks_from_page_texts(broken_pages, "doc", 1, "manual.pdf")


def test_s3_provenance_must_match_database_identity() -> None:
    metadata = {"document-id": "air-quality-pro-manual", "version": "1", "pages": "2"}
    validate_object_provenance(metadata, "air-quality-pro-manual", 1)

    with pytest.raises(ValueError, match="document_id"):
        validate_object_provenance(metadata, "otro-manual", 1)
    with pytest.raises(ValueError, match="versión"):
        validate_object_provenance(metadata, "air-quality-pro-manual", 2)


class FakeModel:
    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def get_sentence_embedding_dimension(self) -> int:
        return self.dimension


def test_model_dimension_must_match_vector_384() -> None:
    assert model_dimension(FakeModel(EXPECTED_DIMENSION)) == 384

    with pytest.raises(ValueError, match=r"VECTOR\(384\)"):
        model_dimension(FakeModel(768))


def test_vector_literal_rejects_wrong_dimension() -> None:
    with pytest.raises(ValueError, match="se esperaban 384"):
        vector_literal([0.1, 0.2])

    rendered = vector_literal([0.0] * EXPECTED_DIMENSION)
    assert rendered.startswith("[") and rendered.endswith("]")
    assert rendered.count(",") == EXPECTED_DIMENSION - 1


def test_e5_prefixes_distinguish_passages_from_queries() -> None:
    chunk = chunks_from_page_texts(
        PAGE_TEXTS, "air-quality-pro-manual", 1, "manuales/manual.pdf"
    )[0]

    assert passage_text(chunk).startswith("passage: Preparación y condiciones.")
    assert query_text("¿Cómo calibro el sensor?") == "query: ¿Cómo calibro el sensor?"


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
    cursor = ThresholdCursor([0.199999, 0.20, 0.200001])

    rows: list[tuple[Any, ...]] = nearest_manual_chunks(  # type: ignore[assignment]
        cursor, "[vector]", 4
    )

    assert [row[-1] for row in rows] == [0.199999, 0.20]
    normalized_sql = " ".join(cursor.sql.split())
    assert normalized_sql.index("WHERE cosine_distance <= %s") < normalized_sql.index(
        "ORDER BY cosine_distance"
    ) < normalized_sql.index("LIMIT %s")
    assert cursor.params == ("[vector]", MAX_COSINE_DISTANCE, 4)
    assert MAX_COSINE_DISTANCE == 0.20


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


@pytest.mark.parametrize("threshold", [-0.1, 0.21, math.inf, math.nan, True])
def test_low_level_retrieval_rejects_unsafe_cosine_cutoff_before_sql(
    threshold: Any,
) -> None:
    cursor = ThresholdCursor([0.1])

    with pytest.raises(ValueError, match="corte coseno"):
        nearest_manual_chunks(
            cursor, "[vector]", 4, max_cosine_distance=threshold
        )

    assert cursor.sql == ""


def test_corpus_calibration_keeps_positive_and_rejects_negative_distances() -> None:
    cursor = ThresholdCursor([0.139691, 0.140339, 0.198, 0.214340, 0.275161])

    rows: list[tuple[Any, ...]] = nearest_manual_chunks(  # type: ignore[assignment]
        cursor, "[vector]", 4
    )

    assert [row[-1] for row in rows] == [0.139691, 0.140339, 0.198]


def test_native_sql_exposes_cosine_and_literal_operators() -> None:
    sql_path = Path(__file__).resolve().parents[1] / "postgres/examples/04-vector.sql"
    sql = sql_path.read_text(encoding="utf-8")

    assert "<=>" in sql
    assert "ILIKE" in sql
    assert "desviado" in sql
