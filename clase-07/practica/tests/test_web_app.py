from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg  # type: ignore[import-not-found]
import pytest  # type: ignore[import-not-found]
from fastapi.testclient import TestClient  # type: ignore[import-not-found]

from api import web_app, workflows  # type: ignore[import-not-found]
from api.openrouter_client import OpenRouterClient  # type: ignore[import-not-found]
from shared.sql_guard import SQLRejected  # type: ignore[import-not-found]
from shared.sql_query import QueryResult  # type: ignore[import-not-found]
from shared.sql_schema import SchemaPrompt  # type: ignore[import-not-found]
from shared.tenants import resolve_user  # type: ignore[import-not-found]

ANA = resolve_user("ana")
ANA_USER = {"id": "ana", "label": "Ana — Organización A"}

VALID_SQL = (
    "SELECT AVG(value) AS average_co2 FROM measurements "
    "WHERE device_id = 'AIR-002' AND variable = 'co2' "
    "AND measured_at >= '2025-05-12T00:00:00Z' "
    "AND measured_at < '2025-05-13T00:00:00Z'"
)
FAKE_SCHEMA = SchemaPrompt("public.measurements\n  variable text\n  value numeric", "database")


@pytest.fixture(autouse=True)
def _fake_live_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    # Workflow tests must not depend on the database: the live schema has its own tests.
    monkeypatch.setattr(workflows, "schema_prompt", lambda _tenant_id: FAKE_SCHEMA)
CHUNKS = [
    {
        "document_id": "upload-0123456789abcdef01234567",
        "version": 1,
        "page": 1,
        "section": "Recalibración tras reemplazo de batería",
        "chunk_index": 1,
        "object_key": "documentos/upload-0123456789abcdef01234567/v1/manual.pdf",
        "content": "Aplicá un único ajuste cuando la diferencia supere el límite.",
        "cosine_distance": 0.12,
    }
]
RESULT = QueryResult(
    columns=("average_co2",),
    rows=({"average_co2": 805.67},),
    byte_count=24,
)


class FakeChat:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[list[dict[str, str]], int]] = []

    def chat(
        self, messages: list[dict[str, str]], *, max_completion_tokens: int
    ) -> str:
        self.calls.append((messages, max_completion_tokens))
        return self.responses.pop(0)


def test_rag_retrieves_before_chat_and_preserves_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    chat = FakeChat("Usá el patrón de referencia [página 1].")

    def retrieve(question: str, top_k: int) -> list[dict[str, Any]]:
        events.append(f"retrieve-{top_k}")
        return CHUNKS

    original_chat = chat.chat

    def observed_chat(*args: Any, **kwargs: Any) -> str:
        events.append("chat")
        return original_chat(*args, **kwargs)

    chat.chat = observed_chat  # type: ignore[method-assign]
    monkeypatch.setattr(workflows, "retrieve_manual", retrieve)

    response = workflows.run_rag("¿Cómo calibro AIR-002?", 1, client=chat)  # type: ignore[arg-type]

    assert events == ["retrieve-1", "chat"]
    assert response["sql"] is None and response["rows"] == []
    assert response["sources"][0] == {
        "type": "manual",
        **CHUNKS[0],
    }
    system_prompt = chat.calls[0][0][0]["content"]
    assert "evidencia no confiable" in system_prompt
    assert chat.calls[0][1] <= 300


def test_rag_without_relevant_chunks_never_calls_openrouter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = FakeChat("no debe consumirse")
    monkeypatch.setattr(workflows, "retrieve_manual", lambda _q, _k: [])

    response = workflows.run_rag("¿Cuál es el precio y el clima?", 4, client=chat)  # type: ignore[arg-type]

    assert chat.calls == []
    assert response["sources"] == []
    assert "evidencia suficiente" in response["answer"]


def test_rag_selected_document_passes_keyword_and_keeps_filtered_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = "upload-0123456789abcdef01234567"
    selected_chunks = [{**CHUNKS[0], "document_id": document_id}]
    observed: list[tuple[str, int, str]] = []
    chat = FakeChat("Respuesta respaldada por el documento seleccionado.")

    def retrieve(
        question: str, top_k: int, *, document_id: str
    ) -> list[dict[str, Any]]:
        observed.append((question, top_k, document_id))
        return selected_chunks

    monkeypatch.setattr(workflows, "retrieve_manual", retrieve)

    response = workflows.run_rag(
        "¿Qué indica el informe?", 2, document_id=document_id, client=chat  # type: ignore[arg-type]
    )

    assert observed == [("¿Qué indica el informe?", 2, document_id)]
    assert response["sources"][0]["document_id"] == document_id
    assert response["sources"][0]["object_key"] == CHUNKS[0]["object_key"]
    assert len(chat.calls) == 1


def test_rag_selected_document_without_evidence_does_not_broaden_or_call_ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = "upload-0123456789abcdef01234567"
    observed: list[str] = []
    chat = FakeChat("no debe consumirse")

    def retrieve(
        _question: str, _top_k: int, *, document_id: str
    ) -> list[dict[str, Any]]:
        observed.append(document_id)
        return []

    monkeypatch.setattr(workflows, "retrieve_manual", retrieve)

    response = workflows.run_rag(
        "¿Qué indica el informe?", 4, document_id=document_id, client=chat  # type: ignore[arg-type]
    )

    assert observed == [document_id]
    assert response["sources"] == []
    assert chat.calls == []
    assert any("sin-resultados" in step for step in response["trace"])


def test_text_to_sql_validates_then_executes_with_ui_friendly_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = FakeChat(VALID_SQL, "El promedio de CO2 fue 805,67 ppm.")
    observed: list[str] = []

    def execute(validated: Any, _tenant_id: int) -> QueryResult:
        observed.append(validated.sql)
        return RESULT

    monkeypatch.setattr(workflows, "execute_validated_sql", execute)
    response = workflows.run_text_to_sql("Promedio de CO2 del día", 3, tenant=ANA, client=chat)  # type: ignore[arg-type]

    assert observed == [response["sql"]]
    assert response["sql"].startswith("SELECT AVG(value)")
    assert response["rows"] == [{"average_co2": 805.67}]
    assert response["sources"][0]["type"] == "telemetry"
    assert response["answer"] == "El promedio de CO2 fue 805,67 ppm."
    assert "openrouter-respuesta" in response["trace"]
    assert len(chat.calls) == 2

    system_prompt = chat.calls[0][0][0]["content"]
    assert FAKE_SCHEMA.text in system_prompt
    assert "sólo lectura" in system_prompt
    assert "JOIN" in system_prompt
    assert "sin JOIN" not in system_prompt
    assert "esquema-database" in response["trace"]

    answer_prompt = chat.calls[1][0][0]["content"]
    assert "evidencia no confiable" in answer_prompt
    assert "FILAS" in chat.calls[1][0][1]["content"]


def test_text_to_sql_reports_null_average_as_no_data_and_keeps_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = FakeChat(VALID_SQL)
    null_result = QueryResult(
        columns=("average_co2",),
        rows=({"average_co2": None},),
        byte_count=8,
    )
    monkeypatch.setattr(workflows, "execute_validated_sql", lambda _validated, _tenant_id: null_result)

    response = workflows.run_text_to_sql("Promedio de CO2 del día", 3, tenant=ANA, client=chat)  # type: ignore[arg-type]

    assert response["sql"].startswith("SELECT AVG(value)")
    assert response["rows"] == [{"average_co2": None}]
    assert "sin datos" in response["answer"].lower()
    assert "revisá los filtros y las mayúsculas" in response["answer"].lower()
    assert "validada y ejecutada" not in response["answer"]
    assert len(chat.calls) == 1
    assert "openrouter-respuesta" not in response["trace"]


BOTH_BRANCHES_PLAN = (
    '{"telemetry_question": "¿Cuál es la telemetría?", '
    '"manual_question": "¿Qué dice el manual?"}'
)
TELEMETRY_ONLY_PLAN = (
    '{"telemetry_question": "¿Cuál es la telemetría?", "manual_question": null}'
)
MANUAL_ONLY_PLAN = (
    '{"telemetry_question": null, "manual_question": "¿Qué dice el manual?"}'
)


def test_integrated_returns_telemetry_and_manual_sources_without_claiming_citation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = FakeChat(BOTH_BRANCHES_PLAN, VALID_SQL, "El promedio de CO2 fue 805,67 ppm.")
    monkeypatch.setattr(workflows, "execute_validated_sql", lambda _validated, _tenant_id: RESULT)
    monkeypatch.setattr(workflows, "retrieve_manual", lambda _q, _k: CHUNKS)

    response = workflows.run_integrated("¿Qué indica AIR-002?", 2, tenant=ANA, client=chat)  # type: ignore[arg-type]

    assert response["sql"] and response["rows"]
    assert [source["type"] for source in response["sources"]] == [
        "telemetry",
        "manual",
    ]
    assert response["sources"][1]["page"] == 1
    assert response["sources"][1]["section"] == "Recalibración tras reemplazo de batería"
    assert response["trace"][0] == "orquestador"
    assert "orquestador-fallback" not in response["trace"]
    assert len(chat.calls) == 3
    assert all(call[1] <= 300 for call in chat.calls)
    system_prompt = chat.calls[2][0][0]["content"]
    assert "evidencia no confiable" in system_prompt
    assert "lista de fuentes no verifica" in system_prompt
    assert "Comprobación" in system_prompt
    assert "criterios de aceptación" in system_prompt
    assert "Recuperación segura" in system_prompt
    assert "evidencia suficiente" in system_prompt
    assert "Evidencia manual citada" not in response["answer"]
    assert "página 1" not in response["answer"]
    assert "Recalibración tras reemplazo de batería" not in response["answer"]


def test_integrated_without_manual_skips_synthesis_and_rejects_fabricated_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fabricated = (
        "Según p. 99, sección secreta del documento manual-falso, "
        "el promedio fue 9999 ppm."
    )
    chat = FakeChat(BOTH_BRANCHES_PLAN, VALID_SQL, fabricated)
    monkeypatch.setattr(workflows, "execute_validated_sql", lambda _validated, _tenant_id: RESULT)
    monkeypatch.setattr(workflows, "retrieve_manual", lambda _q, _k: [])

    response = workflows.run_integrated("¿Cuál fue el promedio de CO2?", 4, tenant=ANA, client=chat)  # type: ignore[arg-type]

    assert response["rows"] == [{"average_co2": 805.67}]
    assert [source["type"] for source in response["sources"]] == ["telemetry"]
    assert len(chat.calls) == 2
    assert "Sin evidencia manual" in response["answer"]
    assert "p. 99" not in response["answer"]
    assert "sección secreta" not in response["answer"]
    assert "manual-falso" not in response["answer"]
    assert "sin-evidencia-manual" in response["trace"]
    assert "sin-openrouter-síntesis" in response["trace"]
    assert "openrouter-síntesis" not in response["trace"]


def test_integrated_selected_document_without_evidence_keeps_only_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = "upload-0123456789abcdef01234567"
    chat = FakeChat(BOTH_BRANCHES_PLAN, VALID_SQL, "no debe consumirse")
    observed: list[str] = []
    monkeypatch.setattr(workflows, "execute_validated_sql", lambda _validated, _tenant_id: RESULT)

    def retrieve(
        _question: str, _top_k: int, *, document_id: str
    ) -> list[dict[str, Any]]:
        observed.append(document_id)
        return []

    monkeypatch.setattr(workflows, "retrieve_manual", retrieve)

    response = workflows.run_integrated(
        "¿Qué indica AIR-002?",
        2,
        document_id=document_id,
        tenant=ANA,
        client=chat,  # type: ignore[arg-type]
    )

    assert observed == [document_id]
    assert [source["type"] for source in response["sources"]] == ["telemetry"]
    assert len(chat.calls) == 2
    assert "sin-evidencia-manual" in response["trace"]
    assert "sin-openrouter-síntesis" in response["trace"]


def test_integrated_orchestrator_routes_telemetry_only_without_manual_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = FakeChat(TELEMETRY_ONLY_PLAN, VALID_SQL)
    monkeypatch.setattr(workflows, "execute_validated_sql", lambda _validated, _tenant_id: RESULT)

    def must_not_retrieve(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        raise AssertionError("manual retrieval must not run for a telemetry-only plan")

    monkeypatch.setattr(workflows, "retrieve_manual", must_not_retrieve)

    response = workflows.run_integrated(
        "¿Cuál fue la temperatura promedio del Aula 204?", 2, tenant=ANA, client=chat  # type: ignore[arg-type]
    )

    assert response["sql"] and response["rows"] == [{"average_co2": 805.67}]
    assert [source["type"] for source in response["sources"]] == ["telemetry"]
    assert len(chat.calls) == 2
    assert "sin-evidencia-manual" in response["trace"]
    assert "modelo-embeddings-local" not in response["trace"]


def test_integrated_orchestrator_routes_manual_only_without_sql_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = FakeChat(MANUAL_ONLY_PLAN, "El manual indica recalibrar tras la batería.")

    def must_not_generate_sql(*_args: Any, **_kwargs: Any) -> str:
        raise AssertionError("SQL generation must not run for a manual-only plan")

    monkeypatch.setattr(workflows, "_generate_sql", must_not_generate_sql)
    monkeypatch.setattr(workflows, "retrieve_manual", lambda _q, _k: CHUNKS)

    response = workflows.run_integrated(
        "¿Cómo debe recalibrarse el sensor?", 2, tenant=ANA, client=chat  # type: ignore[arg-type]
    )

    assert response["sql"] is None
    assert response["rows"] == []
    assert [source["type"] for source in response["sources"]] == ["manual"]
    assert len(chat.calls) == 2
    assert "openrouter-sql" not in response["trace"]
    assert "openrouter-síntesis" in response["trace"]


def test_integrated_malformed_plan_falls_back_to_running_both_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = FakeChat("esto no es JSON", VALID_SQL, "Respuesta combinada.")
    monkeypatch.setattr(workflows, "execute_validated_sql", lambda _validated, _tenant_id: RESULT)
    monkeypatch.setattr(workflows, "retrieve_manual", lambda _q, _k: CHUNKS)

    response = workflows.run_integrated("¿Qué indica AIR-002?", 2, tenant=ANA, client=chat)  # type: ignore[arg-type]

    assert "orquestador-fallback" in response["trace"]
    assert [source["type"] for source in response["sources"]] == [
        "telemetry",
        "manual",
    ]
    assert len(chat.calls) == 3


def test_generated_bad_sql_is_rejected_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = FakeChat("DELETE FROM measurements", "DROP TABLE measurements")
    executed = False

    def must_not_execute(_: Any, _tenant_id: int) -> QueryResult:
        nonlocal executed
        executed = True
        return RESULT

    monkeypatch.setattr(workflows, "execute_validated_sql", must_not_execute)
    with pytest.raises(SQLRejected, match="lectura"):
        workflows.run_text_to_sql("Borrá todo", 2, tenant=ANA, client=chat)  # type: ignore[arg-type]
    assert executed is False
    assert len(chat.calls) == 2


def test_failed_sql_is_retried_once_with_the_database_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = FakeChat("SELECT nope FROM measurements", VALID_SQL, "El promedio fue 805,67 ppm.")
    attempts: list[str] = []

    def execute(validated: Any, _tenant_id: int) -> QueryResult:
        attempts.append(validated.sql)
        if len(attempts) == 1:
            raise psycopg.errors.UndefinedColumn('column "nope" does not exist')
        return RESULT

    monkeypatch.setattr(workflows, "execute_validated_sql", execute)

    response = workflows.run_text_to_sql("Promedio de CO2", 2, tenant=ANA, client=chat)  # type: ignore[arg-type]

    assert len(attempts) == 2
    assert "reintento-sql" in response["trace"]
    retry_messages = chat.calls[1][0]
    assert any('column "nope" does not exist' in message["content"] for message in retry_messages)
    assert response["rows"] == [{"average_co2": 805.67}]


def test_sql_failing_twice_is_reported_as_a_visible_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = FakeChat("SELECT nope FROM measurements", "SELECT nope2 FROM measurements")

    def execute(_validated: Any, _tenant_id: int) -> QueryResult:
        raise psycopg.errors.UndefinedColumn('column "nope" does not exist')

    monkeypatch.setattr(workflows, "execute_validated_sql", execute)

    with pytest.raises(SQLRejected, match="does not exist"):
        workflows.run_text_to_sql("Promedio de CO2", 2, tenant=ANA, client=chat)  # type: ignore[arg-type]


@pytest.mark.parametrize("mode", ["rag", "text-to-sql", "integrated"])
def test_api_exposes_all_three_modes(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = {
        "answer": f"respuesta {mode}",
        "sql": VALID_SQL if mode != "rag" else None,
        "rows": [{"value": 1}] if mode != "rag" else [],
        "sources": [{"type": "manual"}],
        "trace": [mode],
    }
    monkeypatch.setitem(
        workflows.WORKFLOWS, mode, lambda _question, _top_k, *, tenant: expected
    )

    response = TestClient(web_app.app).post(
        "/api/query",
        json={"question": "¿Qué ocurrió?", "mode": mode, "top_k": 2, "user_id": "ana"},
    )

    assert response.status_code == 200
    assert response.json() == {**expected, "user": ANA_USER}


def test_api_accepts_a_free_text_question_not_present_in_examples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom_question = "¿Qué sensores informaron humedad durante el turno nocturno?"
    observed: list[tuple[str, int]] = []
    expected = {
        "answer": "respuesta simulada",
        "sql": None,
        "rows": [],
        "sources": [],
        "trace": ["rag"],
    }

    def rag(question: str, top_k: int, *, tenant: Any) -> dict[str, Any]:
        observed.append((question, top_k))
        return expected

    monkeypatch.setitem(workflows.WORKFLOWS, "rag", rag)
    response = TestClient(web_app.app).post(
        "/api/query",
        json={"question": custom_question, "mode": "rag", "top_k": 4, "user_id": "ana"},
    )

    assert response.status_code == 200
    assert response.json() == {**expected, "user": ANA_USER}
    assert observed == [(custom_question, 4)]


def test_api_uses_four_manual_chunks_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[str, int]] = []
    expected = {
        "answer": "respuesta integrada",
        "sql": VALID_SQL,
        "rows": [{"average_co2": 805.67}],
        "sources": [],
        "trace": ["integrated"],
    }

    def integrated(question: str, top_k: int, *, tenant: Any) -> dict[str, Any]:
        observed.append((question, top_k))
        return expected

    monkeypatch.setitem(workflows.WORKFLOWS, "integrated", integrated)
    response = TestClient(web_app.app).post(
        "/api/query",
        json={"question": "¿Cómo reinicio si falla?", "mode": "integrated", "user_id": "ana"},
    )

    assert response.status_code == 200
    assert response.json() == {**expected, "user": ANA_USER}
    assert observed == [("¿Cómo reinicio si falla?", 4)]


def test_root_serves_accessible_static_ui_with_safe_dom_rendering() -> None:
    response = TestClient(web_app.app).get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert '<select id="mode"' in html
    assert all(mode in html for mode in ("rag", "text-to-sql", "integrated"))
    assert '<textarea id="question" name="question" required minlength="3" maxlength="500"' in html
    assert 'aria-describedby="question-help"></textarea>' in html
    assert "<datalist" not in html
    assert 'list="sample-prompts"' not in html
    assert html.count('class="example" type="button"') == 3
    assert "example.addEventListener('click'" in html
    assert "question.focus()" in html
    assert "Escribí tu propia pregunta" in html
    assert "rol de sólo lectura" in html
    assert "lab_read" not in html
    assert "Resumí los puntos principales de los documentos cargados" in html
    assert "¿Cuál fue la temperatura promedio del Aula 204" in html
    assert "El sensor AMB-001 del Aula 204 presenta mediciones anómalas" in html
    assert "ENV-X" not in html
    assert 'id="top-k" name="top_k" type="number" min="1" max="4" value="4"' in html
    assert "fetch('/api/query'" in html
    assert ".textContent" in html
    assert "innerHTML" not in html
    assert "OPENROUTER_API_KEY" not in html
    assert "OpenRouter pueden tener costo" in html
    assert "corte de evidencia es aproximado" in html


def test_missing_key_only_blocks_ai_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setitem(
        workflows.WORKFLOWS, "text-to-sql", workflows.run_text_to_sql
    )
    client = TestClient(web_app.app)

    assert client.get("/health").json() == {"status": "ok"}
    response = client.post(
        "/api/query",
        json={"question": "Promedio de CO2", "mode": "text-to-sql", "top_k": 2, "user_id": "ana"},
    )

    assert response.status_code == 503
    assert response.json()["detail"].startswith("Falta OPENROUTER_API_KEY")


def test_request_validation_and_visible_sql_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject(_question: str, _top_k: int, *, tenant: Any) -> dict[str, Any]:
        raise SQLRejected("se permite exactamente una sentencia SELECT", "DROP TABLE x")

    monkeypatch.setitem(workflows.WORKFLOWS, "text-to-sql", reject)
    client = TestClient(web_app.app)
    invalid = client.post(
        "/api/query", json={"question": "  ", "mode": "rag", "top_k": 5, "user_id": "ana"}
    )
    rejected = client.post(
        "/api/query",
        json={"question": "Consulta insegura", "mode": "text-to-sql", "top_k": 2, "user_id": "ana"},
    )

    assert invalid.status_code == 422
    assert rejected.status_code == 422
    assert "Consulta rechazada" in rejected.json()["detail"]


def test_app_service_has_only_restricted_database_credentials() -> None:
    compose = (
        Path(__file__).resolve().parents[1] / "compose.yaml"
    ).read_text(encoding="utf-8")
    app_block = compose.split("\n  app:\n", 1)[1].split("\n  seaweedfs:\n", 1)[0]
    environment_block = app_block.split("    environment:\n", 1)[1].split(
        "    volumes:\n", 1
    )[0]
    keys = {
        line.strip().split(":", 1)[0]
        for line in environment_block.splitlines()
        if line.strip()
    }

    assert "POSTGRES_USER" not in keys
    assert "POSTGRES_PASSWORD" not in keys
    assert {"RAG_POSTGRES_USER", "AI_POSTGRES_USER", "OPENROUTER_API_KEY"} <= keys
    assert '"127.0.0.1:${APP_PORT:-8007}:8006"' in app_block


def test_database_and_model_failures_become_sanitized_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenModel:
        def encode(self, *_args: Any, **_kwargs: Any) -> list[float]:
            raise RuntimeError("private model cache /secret/path")

    monkeypatch.setattr(workflows, "embedding_model", lambda: BrokenModel())
    monkeypatch.setitem(workflows.WORKFLOWS, "rag", workflows.run_rag)
    client = TestClient(web_app.app)

    model_response = client.post(
        "/api/query",
        json={"question": "¿Cómo calibro?", "mode": "rag", "top_k": 2, "user_id": "ana"},
    )
    assert model_response.status_code == 503
    assert model_response.json() == {
        "detail": "El modelo local de recuperación no está disponible temporalmente."
    }
    assert "secret" not in model_response.text

    class WorkingModel:
        def encode(self, *_args: Any, **_kwargs: Any) -> list[float]:
            return [0.0] * 1024

    def fail_connect(**_kwargs: Any) -> Any:
        raise psycopg.OperationalError("host=private password=supersecret timeout")

    monkeypatch.setattr(workflows, "embedding_model", lambda: WorkingModel())
    monkeypatch.setattr(workflows.psycopg, "connect", fail_connect)
    monkeypatch.setenv("RAG_POSTGRES_PASSWORD", "not-returned")
    database_response = client.post(
        "/api/query",
        json={"question": "¿Cómo calibro?", "mode": "rag", "top_k": 2, "user_id": "ana"},
    )

    assert database_response.status_code == 503
    assert database_response.json() == {
        "detail": "La base de evidencia no está disponible temporalmente."
    }
    assert "private" not in database_response.text
    assert "password" not in database_response.text
    assert "supersecret" not in database_response.text


def test_sql_database_failure_is_typed_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = FakeChat(VALID_SQL)

    def fail_sql(_validated: Any, _tenant_id: int) -> QueryResult:
        raise psycopg.OperationalError("dbname=private password=supersecret")

    monkeypatch.setattr(workflows, "execute_validated_sql", fail_sql)

    with pytest.raises(workflows.ServiceUnavailable) as captured:
        workflows.run_text_to_sql("Promedio de CO2", 2, tenant=ANA, client=chat)  # type: ignore[arg-type]

    assert str(captured.value) == "La base de telemetría no está disponible temporalmente."
    assert "supersecret" not in str(captured.value)


def test_openrouter_client_rejects_missing_key_without_network() -> None:
    with pytest.raises(RuntimeError, match="Falta OPENROUTER_API_KEY"):
        OpenRouterClient(api_key="")
