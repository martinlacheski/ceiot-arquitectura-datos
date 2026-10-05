"""The Text-to-SQL schema is discovered from the database, never hardcoded."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg  # type: ignore[import-not-found]
import pytest

from shared import sql_schema  # type: ignore[import-not-found]

SNAPSHOT = sql_schema.SchemaSnapshot(
    extensions=[{"name": "timescaledb", "version": "2.30.1"}],
    columns=[
        {"schema": "public", "table": "devices", "table_comment": "Sensores y actuadores",
         "column": "device_id", "type": "text", "column_comment": None},
        {"schema": "public", "table": "devices", "table_comment": "Sensores y actuadores",
         "column": "location_id", "type": "text", "column_comment": "Ubicación del equipo"},
        {"schema": "public", "table": "measurements", "table_comment": None,
         "column": "value", "type": "numeric(12,3)", "column_comment": None},
    ],
    constraints=[
        {"schema": "public", "table": "devices",
         "definition": "FOREIGN KEY (location_id) REFERENCES locations(location_id)"},
    ],
    values={"public.measurements.variable": ["co2", "temperature"]},
)


def test_formats_tables_columns_keys_values_and_extensions() -> None:
    text = sql_schema.format_schema(SNAPSHOT)

    assert "timescaledb 2.30.1" in text
    assert "public.devices -- Sensores y actuadores" in text
    assert "  location_id text -- Ubicación del equipo" in text
    assert "  value numeric(12,3)" in text
    assert "public.devices: FOREIGN KEY (location_id) REFERENCES locations(location_id)" in text
    assert "public.measurements.variable: co2, temperature" in text


def test_python_code_does_not_hardcode_any_table_of_the_lab() -> None:
    source = Path(sql_schema.__file__).read_text(encoding="utf-8")

    for table in ("measurements", "devices", "locations", "manual_chunks", "lab_read"):
        assert table not in source


def test_schema_is_cached_for_a_while_and_then_reloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    now = [1000.0]

    def fake_load(_tenant_id: int) -> Any:
        calls.append(1)
        return SNAPSHOT

    monkeypatch.setattr(sql_schema, "_load_from_database", fake_load)
    monkeypatch.setattr(sql_schema.time, "monotonic", lambda: now[0])

    first = sql_schema.schema_prompt(1)
    second = sql_schema.schema_prompt(1)
    now[0] += sql_schema.CACHE_SECONDS + 1
    sql_schema.schema_prompt(1)

    assert first.source == "database"
    assert second == first
    assert len(calls) == 2


def test_unreachable_database_is_reported_not_replaced_by_a_fixed_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_load(_tenant_id: int) -> Any:
        raise psycopg.OperationalError("down")

    monkeypatch.setattr(sql_schema, "_load_from_database", failing_load)

    with pytest.raises(sql_schema.SchemaUnavailable):
        sql_schema.schema_prompt(1)


def test_live_schema_describes_what_ai_readonly_can_read() -> None:
    text = sql_schema.schema_prompt(1).text

    for expected in (
        "public.measurements",
        "public.devices",
        "public.locations",
        "FOREIGN KEY",
        "timescaledb",
        "postgis",
        "co2",
        "AULA-204",
    ):
        assert expected in text
    assert "spatial_ref_sys" not in text
    assert "lab_read" not in text


def test_schema_endpoint_shows_what_the_model_receives(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient  # type: ignore[import-not-found]

    from api import web_app  # type: ignore[import-not-found]

    monkeypatch.setattr(sql_schema, "_load_from_database", lambda _tenant_id: SNAPSHOT)

    response = TestClient(web_app.app).get("/api/sql-schema", params={"user_id": "ana"})

    assert response.status_code == 200
    assert response.json()["source"] == "database"
    assert "public.devices" in response.json()["text"]


def test_long_or_hash_like_values_are_left_out_of_the_prompt() -> None:
    from contextlib import nullcontext

    answers = {
        "variable": [{"v": "co2"}, {"v": "humidity"}],
        "sha256": [{"v": "a" * 64}],
    }

    class FakeConnection:
        def transaction(self) -> Any:
            return nullcontext()

        def execute(self, query: Any) -> Any:
            text = query.as_string(None)
            column = "sha256" if "sha256" in text else "variable"
            rows = answers[column]
            return type("Cursor", (), {"fetchall": lambda _self: rows})()

    columns = [
        {"schema": "public", "table": "t", "column": "variable", "type": "text"},
        {"schema": "public", "table": "t", "column": "sha256", "type": "text"},
    ]

    values = sql_schema._distinct_values(FakeConnection(), columns)  # type: ignore[arg-type]

    assert values == {"public.t.variable": ["co2", "humidity"]}
