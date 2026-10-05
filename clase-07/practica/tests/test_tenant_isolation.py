"""El contexto de tenant llega a la base antes del SQL generado y RLS lo respeta."""

from __future__ import annotations

import os
from typing import Any

import psycopg  # type: ignore[import-not-found]
import pytest  # type: ignore[import-not-found]
from fastapi.testclient import TestClient  # type: ignore[import-not-found]

from api import web_app, workflows  # type: ignore[import-not-found]
from api.openrouter_client import OpenRouterClient  # type: ignore[import-not-found]
from shared import sql_query, sql_schema  # type: ignore[import-not-found]
from shared.sql_guard import validate_sql  # type: ignore[import-not-found]
from shared.sql_query import QueryResult, execute_validated_sql  # type: ignore[import-not-found]
from shared.tenants import resolve_user  # type: ignore[import-not-found]

ANA = resolve_user("ana")
BRUNO = resolve_user("bruno")


# --- orden de ejecución (sin base) ---------------------------------------------


class _FakeCursor:
    description = (type("Column", (), {"name": "n"})(),)

    def fetchmany(self, _size: int) -> list[dict[str, int]]:
        return [{"n": 1}]


class _FakeConnection:
    def __init__(self, log: list[tuple[str, Any]]) -> None:
        self.log = log

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, query: str, params: Any = None) -> _FakeCursor:
        self.log.append((query, params))
        return _FakeCursor()


def test_tenant_context_is_set_inside_the_transaction_before_the_generated_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log: list[tuple[str, Any]] = []
    monkeypatch.setattr(sql_query, "_connection_settings", lambda: {})
    monkeypatch.setattr(sql_query.psycopg, "connect", lambda **_: _FakeConnection(log))

    execute_validated_sql(validate_sql("SELECT 1 AS n"), 2)

    statements = [query for query, _ in log]
    begin = statements.index("BEGIN READ ONLY")
    context = next(i for i, (q, _) in enumerate(log) if "set_config('app.tenant_id'" in q)
    generated = statements.index("SELECT 1 AS n")
    assert begin < context < generated
    assert log[context][1] == ("2",)
    assert statements[-1] == "ROLLBACK"


@pytest.mark.parametrize("bad", [0, -1, "1", None, True, 1.5])
def test_invalid_tenant_ids_never_reach_the_database(
    monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    monkeypatch.setattr(
        sql_query.psycopg, "connect", lambda **_: pytest.fail("no debe conectarse")
    )

    with pytest.raises((TypeError, ValueError)):
        execute_validated_sql(validate_sql("SELECT 1"), bad)  # type: ignore[arg-type]


# --- flujo de trabajo -----------------------------------------------------------


class _FakeChat(OpenRouterClient):
    def __init__(self, *responses: str) -> None:  # noqa: D107
        self.responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, messages: list[dict[str, str]], *, max_completion_tokens: int) -> str:
        self.calls.append(messages)
        return self.responses.pop(0)


def test_text_to_sql_runs_with_the_tenant_and_traces_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[str, int]] = []
    schema_calls: list[int] = []

    def execute(validated: Any, tenant_id: int) -> QueryResult:
        observed.append((validated.sql, tenant_id))
        return QueryResult(("n",), ({"n": 4},), 8)

    def schema(tenant_id: int) -> sql_schema.SchemaPrompt:
        schema_calls.append(tenant_id)
        return sql_schema.SchemaPrompt("public.devices", "database")

    monkeypatch.setattr(workflows, "execute_validated_sql", execute)
    monkeypatch.setattr(workflows, "schema_prompt", schema)
    chat = _FakeChat("SELECT count(*) AS n FROM devices", "Hay 4 equipos.")

    response = workflows.run_text_to_sql("¿Cuántos equipos hay?", 3, tenant=BRUNO, client=chat)

    assert observed == [("SELECT count(*) AS n FROM devices", 2)]
    assert schema_calls == [2]
    assert "tenant=2" in response["trace"]
    assert "rol=ai_readonly" in response["trace"]


def test_sql_prompt_tells_the_model_that_the_database_already_filters_the_organization() -> None:
    prompt = workflows.SQL_SYSTEM_PROMPT

    assert "organización" in prompt
    assert "organization_id" in prompt


# --- base real: RLS con el rol ai_readonly --------------------------------------


def _count(sql: str, tenant: int | None) -> int:
    """Cuenta filas como ai_readonly, con o sin contexto de tenant."""
    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "ceiot_class7"),
        user="ai_readonly",
        password=os.environ["AI_POSTGRES_PASSWORD"],
        autocommit=True,
    ) as connection:
        connection.execute("BEGIN READ ONLY")
        if tenant is not None:
            connection.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant),))
        row = connection.execute(sql).fetchone()
        connection.execute("ROLLBACK")
    assert row is not None
    return int(row[0])


def test_live_ai_readonly_sees_only_its_organization_devices() -> None:
    assert _count("SELECT count(*) FROM devices", 1) == 4
    assert _count("SELECT count(*) FROM devices", 2) == 2


def test_live_filtering_by_another_organization_returns_nothing() -> None:
    assert _count("SELECT count(*) FROM measurements WHERE organization_id = 2", 1) == 0
    assert _count("SELECT count(*) FROM measurements WHERE organization_id = 1", 2) == 0


def test_live_without_context_the_database_fails_closed() -> None:
    for table in ("organizations", "locations", "devices", "measurements"):
        assert _count(f"SELECT count(*) FROM {table}", None) == 0


def test_live_execute_validated_sql_applies_the_tenant() -> None:
    ana = execute_validated_sql(validate_sql("SELECT count(*) AS n FROM devices"), 1)
    bruno = execute_validated_sql(validate_sql("SELECT count(*) AS n FROM devices"), 2)

    assert ana.rows[0]["n"] == 4
    assert bruno.rows[0]["n"] == 2


def test_live_lab_read_views_do_not_bypass_rls() -> None:
    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "ceiot_class7"),
        user=os.getenv("POSTGRES_USER", "ceiot"),
        password=os.environ["POSTGRES_PASSWORD"],
        autocommit=True,
    ) as admin:
        options = admin.execute(
            "SELECT relname, reloptions FROM pg_class "
            "WHERE relnamespace = 'lab_read'::regnamespace AND relkind = 'v' ORDER BY 1"
        ).fetchall()
    assert options
    assert all("security_invoker=true" in (opts or []) for _, opts in options)


# --- esquema descubierto por tenant ----------------------------------------------


def test_live_schema_values_come_only_from_the_requesting_organization() -> None:
    ana = sql_schema.schema_prompt(1).text
    bruno = sql_schema.schema_prompt(2).text

    assert "AULA-204" in ana
    assert "PLANTA-01" not in ana and "PLT-001" not in ana
    assert "PLANTA-01" in bruno
    assert "AULA-204" not in bruno and "AMB-001" not in bruno


def test_schema_cache_is_kept_per_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_load(tenant_id: int) -> sql_schema.SchemaSnapshot:
        calls.append(tenant_id)
        return sql_schema.SchemaSnapshot(values={"public.t.c": [f"org{tenant_id}"]})

    monkeypatch.setattr(sql_schema, "_load_from_database", fake_load)

    first = sql_schema.schema_prompt(1)
    second = sql_schema.schema_prompt(2)
    again = sql_schema.schema_prompt(1)

    assert "org1" in first.text and "org2" not in first.text
    assert "org2" in second.text and "org1" not in second.text
    assert again == first
    assert calls == [1, 2]


def test_schema_endpoint_requires_a_known_user() -> None:
    client = TestClient(web_app.app)

    assert client.get("/api/sql-schema").status_code == 422
    assert client.get("/api/sql-schema", params={"user_id": "mallory"}).status_code == 422


def test_live_schema_endpoint_never_leaks_the_other_organization() -> None:
    client = TestClient(web_app.app)

    ana = client.get("/api/sql-schema", params={"user_id": "ana"}).json()["text"]
    bruno = client.get("/api/sql-schema", params={"user_id": "bruno"}).json()["text"]

    assert "PLANTA-01" not in ana and "PLT-001" not in ana
    assert "AULA-204" not in bruno


# --- interfaz y configuración ------------------------------------------------------


def test_ui_selects_a_simulated_user_and_sends_only_its_id() -> None:
    html = TestClient(web_app.app).get("/").text

    assert '<select id="user-id" name="user_id"' in html
    assert "fetch('/api/users')" in html
    assert "user_id: userSelect.value" in html
    assert "Consultando como:" in html
    assert "organization_id" not in html and "tenant_id" not in html


def test_rls_script_is_mounted_in_the_database_init() -> None:
    from pathlib import Path

    compose = (Path(__file__).resolve().parents[1] / "compose.yaml").read_text(encoding="utf-8")

    assert "07-tenant-rls.sql:/docker-entrypoint-initdb.d/07-tenant-rls.sql:ro" in compose


def test_live_app_iot_role_is_least_privilege() -> None:
    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "ceiot_class7"),
        user=os.getenv("POSTGRES_USER", "ceiot"),
        password=os.environ["POSTGRES_PASSWORD"],
        autocommit=True,
    ) as admin:
        privileges = admin.execute(
            """
            SELECT
                has_table_privilege('app_iot', 'public.measurements', 'INSERT'),
                has_table_privilege('app_iot', 'public.measurements', 'DELETE'),
                has_table_privilege('app_iot', 'public.devices', 'DELETE'),
                has_table_privilege('app_iot', 'public.devices', 'SELECT'),
                has_column_privilege('app_iot', 'public.devices', 'sampling_interval_seconds', 'UPDATE'),
                has_column_privilege('app_iot', 'public.devices', 'model', 'UPDATE'),
                (SELECT NOT rolsuper AND NOT rolbypassrls FROM pg_roles WHERE rolname = 'app_iot'),
                (SELECT bool_and(NOT rolbypassrls) FROM pg_roles
                 WHERE rolname IN ('ai_readonly', 'rag_readonly', 'rag_ingest'))
            """
        ).fetchone()
    assert privileges == (True, False, False, True, True, False, True, True)
