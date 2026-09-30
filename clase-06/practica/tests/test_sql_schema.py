"""Schema description for Text-to-SQL built from the database, not hardcoded."""

from __future__ import annotations

from typing import Any

import psycopg  # type: ignore[import-not-found]
import pytest

from shared import sql_schema  # type: ignore[import-not-found]

COLUMNS = [
    {"table_name": "devices", "column_name": "device_id", "data_type": "text"},
    {"table_name": "devices", "column_name": "model", "data_type": "text"},
    {"table_name": "measurements", "column_name": "measured_at", "data_type": "timestamp with time zone"},
    {"table_name": "measurements", "column_name": "value", "data_type": "numeric"},
]
VALUES = {
    "variable": ["co2", "temperature"],
    "quality": ["GOOD"],
    "device_id": ["AIR-002"],
    "location_id": ["AULA-204"],
    "model": ["ENV-X"],
    "location_name": ["Aula 204"],
}


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    sql_schema.clear_cache()


def test_describes_every_lab_read_view_with_its_columns_and_types() -> None:
    text = sql_schema.format_schema(COLUMNS, VALUES)

    assert "lab_read.devices(\n  device_id text, model text\n)" in text
    assert "lab_read.measurements(\n  measured_at timestamp with time zone, value numeric\n)" in text
    assert "- variable: co2, temperature" in text
    assert "- lab_read.locations.name: Aula 204" in text
    assert "now() - INTERVAL" in text
    assert "case-sensitive" in text


def test_prompt_is_read_from_the_database_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_load() -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
        calls.append(1)
        return COLUMNS, VALUES

    monkeypatch.setattr(sql_schema, "_load_from_database", fake_load)

    first = sql_schema.schema_prompt()
    second = sql_schema.schema_prompt()

    assert first.source == "database"
    assert "lab_read.devices(" in first.text
    assert second == first
    assert len(calls) == 1


def test_empty_database_is_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    empty = {name: [] for name in VALUES}

    def fake_load() -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
        calls.append(1)
        return COLUMNS, empty

    monkeypatch.setattr(sql_schema, "_load_from_database", fake_load)

    first = sql_schema.schema_prompt()
    sql_schema.schema_prompt()

    assert first.source == "static"
    assert len(calls) == 2


def test_unreachable_database_falls_back_to_static_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_load() -> Any:
        raise psycopg.OperationalError("down")

    monkeypatch.setattr(sql_schema, "_load_from_database", failing_load)

    prompt = sql_schema.schema_prompt()

    assert prompt.source == "static"
    assert prompt.text == sql_schema.STATIC_SQL_SCHEMA


def test_schema_endpoint_shows_what_the_model_receives(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient  # type: ignore[import-not-found]

    from api import web_app  # type: ignore[import-not-found]

    monkeypatch.setattr(sql_schema, "_load_from_database", lambda: (COLUMNS, VALUES))

    response = TestClient(web_app.app).get("/api/sql-schema")

    assert response.status_code == 200
    assert response.json()["source"] == "database"
    assert "lab_read.devices(" in response.json()["text"]


def test_text_to_sql_prompt_and_trace_use_the_database_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import workflows  # type: ignore[import-not-found]

    monkeypatch.setattr(sql_schema, "_load_from_database", lambda: (COLUMNS, VALUES))
    seen: list[str] = []

    class FakeClient:
        def chat(self, messages: list[dict[str, str]], **_kwargs: Any) -> str:
            seen.append(messages[0]["content"])
            return "SELECT count(*) AS n FROM lab_read.measurements LIMIT 1"

    monkeypatch.setattr(
        workflows,
        "_execute_sql_safely",
        lambda _validated: workflows.QueryResult(columns=("n",), rows=(), byte_count=0),
    )

    response = workflows.run_text_to_sql("¿Cuántas mediciones hay?", 1, client=FakeClient())

    assert "- variable: co2, temperature" in seen[0]
    assert "esquema-database" in response["trace"]
