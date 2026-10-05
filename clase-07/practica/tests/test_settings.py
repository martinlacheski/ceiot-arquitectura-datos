"""Configuración por variables de entorno: defaults, overrides y fallas claras."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest  # type: ignore[import-not-found]

COMPOSE = (Path(__file__).resolve().parents[1] / "compose.yaml").read_text(encoding="utf-8")
ENV_EXAMPLE = (Path(__file__).resolve().parents[1] / ".env.example").read_text(
    encoding="utf-8"
)


@pytest.fixture
def reload_with_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Any]]:
    """Recarga un módulo con variables de entorno y lo restaura al terminar."""

    touched: list[Any] = []

    def _reload(module_name: str, **env: str) -> Any:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        module = importlib.import_module(module_name)
        touched.append(module)
        return importlib.reload(module)

    yield _reload
    monkeypatch.undo()
    # Orden de importación: primero las dependencias y luego quien las usa.
    for module in touched:
        importlib.reload(module)


def run_python(code: str, **env: str) -> subprocess.CompletedProcess[str]:
    """Ejecuta código en un intérprete nuevo: sirve para módulos que definen clases."""

    return subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )


def _service(name: str) -> str:
    after = COMPOSE.split(f"\n  {name}:\n", 1)[1]
    return after.split("\n\n  ", 1)[0]


# --- helper genérico -------------------------------------------------------


def test_env_int_uses_default_and_treats_blank_as_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared.settings import env_int  # type: ignore[import-not-found]

    monkeypatch.delenv("X_TEST_INT", raising=False)
    assert env_int("X_TEST_INT", 7) == 7
    monkeypatch.setenv("X_TEST_INT", "  ")
    assert env_int("X_TEST_INT", 7) == 7
    monkeypatch.setenv("X_TEST_INT", " 12 ")
    assert env_int("X_TEST_INT", 7, minimum=1, maximum=20) == 12


@pytest.mark.parametrize("raw", ["abc", "1.5", "0", "21", "-3", "1e3"])
def test_env_int_rejects_invalid_values_naming_the_variable(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    from shared.settings import env_int  # type: ignore[import-not-found]

    monkeypatch.setenv("X_TEST_INT", raw)
    with pytest.raises(ValueError, match="X_TEST_INT"):
        env_int("X_TEST_INT", 7, minimum=1, maximum=20)


def test_env_float_accepts_range_and_rejects_non_finite_or_out_of_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared.settings import env_float  # type: ignore[import-not-found]

    monkeypatch.delenv("X_TEST_FLOAT", raising=False)
    assert env_float("X_TEST_FLOAT", 0.55, minimum=0.0, maximum=2.0) == 0.55
    monkeypatch.setenv("X_TEST_FLOAT", "0.4")
    assert env_float("X_TEST_FLOAT", 0.55, minimum=0.0, maximum=2.0) == 0.4
    for raw in ("nan", "inf", "-0.1", "2.5", "abc"):
        monkeypatch.setenv("X_TEST_FLOAT", raw)
        with pytest.raises(ValueError, match="X_TEST_FLOAT"):
            env_float("X_TEST_FLOAT", 0.55, minimum=0.0, maximum=2.0)


def test_env_str_default_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    from shared.settings import env_str  # type: ignore[import-not-found]

    monkeypatch.delenv("X_TEST_STR", raising=False)
    assert env_str("X_TEST_STR", "a/b") == "a/b"
    monkeypatch.setenv("X_TEST_STR", " otro ")
    assert env_str("X_TEST_STR", "a/b") == "otro"


# --- defaults actuales -----------------------------------------------------


def test_defaults_match_previous_fixed_values() -> None:
    from api import openrouter_client
    from loader import pdf_document, seed_services
    from shared import embeddings, retrieval

    assert embeddings.MODEL_NAME == "BAAI/bge-m3"
    assert embeddings.EXPECTED_DIMENSION == 1024
    assert embeddings.EMBEDDING_BATCH_SIZE == 4
    assert retrieval.MAX_COSINE_DISTANCE == 0.55
    assert retrieval.MAX_TOP_K == 4
    assert pdf_document.MAX_PDF_BYTES == 50 * 1024 * 1024
    assert pdf_document.MAX_CHUNK_CHARS == 1200
    assert pdf_document.CHUNK_OVERLAP_CHARS == 150
    assert seed_services.REDIS_TTL_SECONDS == 3600
    assert openrouter_client.MAX_COMPLETION_TOKENS == 300


# --- overrides -------------------------------------------------------------


def test_retrieval_limits_follow_environment(reload_with_env: Callable[..., Any]) -> None:
    retrieval = reload_with_env(
        "shared.retrieval", RAG_MAX_COSINE_DISTANCE="0.4", RAG_MAX_TOP_K="6"
    )

    assert retrieval.MAX_COSINE_DISTANCE == 0.4
    assert retrieval.MAX_TOP_K == 6


def test_top_k_validation_message_uses_configured_limit(
    reload_with_env: Callable[..., Any],
) -> None:
    retrieval = reload_with_env("shared.retrieval", RAG_MAX_TOP_K="6")

    class Cursor:
        def execute(self, *_a: Any) -> None: ...
        def fetchall(self) -> list[Any]:
            return []

    assert retrieval.nearest_manual_chunks(Cursor(), "[v]", 6) == []
    with pytest.raises(ValueError, match="entre 1 y 6"):
        retrieval.nearest_manual_chunks(Cursor(), "[v]", 7)


def test_pdf_limits_follow_environment() -> None:
    result = run_python(
        "from loader import pdf_document as p;"
        "print(p.MAX_PDF_BYTES, p.MAX_CHUNK_CHARS, p.CHUNK_OVERLAP_CHARS);"
        "\ntry: p.parse_document(b'', 'Informe', 'application/pdf')\n"
        "except p.PDFRejected as e: print(e.reason)",
        MAX_PDF_MIB="10",
        CHUNK_MAX_CHARS="800",
        CHUNK_OVERLAP_CHARS="100",
    )

    assert result.returncode == 0, result.stderr
    first, second = result.stdout.strip().splitlines()
    assert first == f"{10 * 1024 * 1024} 800 100"
    assert "10 MiB" in second


def test_embedding_settings_follow_environment(
    reload_with_env: Callable[..., Any],
) -> None:
    embeddings = reload_with_env(
        "shared.embeddings", MODELO_EMBEDDING="otro/modelo", EMBEDDING_BATCH_SIZE="2"
    )

    assert embeddings.MODEL_NAME == "otro/modelo"
    assert embeddings.EMBEDDING_BATCH_SIZE == 2


def test_configured_model_name_is_loaded_without_fixed_name_rejection(
    monkeypatch: pytest.MonkeyPatch, reload_with_env: Callable[..., Any]
) -> None:
    embeddings = reload_with_env("shared.embeddings", MODELO_EMBEDDING="otro/modelo")
    loaded: list[str] = []

    class FakeModel:
        def __init__(self, name: str, device: str) -> None:
            loaded.append(name)

        def get_sentence_embedding_dimension(self) -> int:
            return 1024

    monkeypatch.setattr(embeddings, "SentenceTransformer", FakeModel)
    embeddings.embedding_model.cache_clear()

    assert embeddings.embedding_model() is not None
    assert loaded == ["otro/modelo"]


def test_model_with_other_dimension_fails_clearly_in_spanish() -> None:
    from shared import embeddings

    class Wide:
        def get_sentence_embedding_dimension(self) -> int:
            return 768

    with pytest.raises(ValueError) as captured:
        embeddings.model_dimension(Wide())
    message = str(captured.value)
    assert "768" in message and "VECTOR(1024)" in message
    assert embeddings.MODEL_NAME in message


def test_redis_ttl_follows_environment(reload_with_env: Callable[..., Any]) -> None:
    seed = reload_with_env("loader.seed_services", REDIS_TTL_SECONDS="120")

    assert seed.REDIS_TTL_SECONDS == 120


def test_completion_cap_is_a_global_ceiling_not_an_error() -> None:
    code = """
import httpx
from api import openrouter_client as m

sent = []

class R:
    def raise_for_status(self): pass
    def json(self): return {"choices": [{"message": {"content": "ok"}}]}

class C:
    def __init__(self, **kw): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def post(self, url, **kw):
        sent.append(kw["json"]["max_completion_tokens"]); return R()

httpx.Client = C
client = m.OpenRouterClient(api_key="k", model="m")
assert client.chat([], max_completion_tokens=260) == "ok"
assert client.chat([], max_completion_tokens=120) == "ok"
print(m.MAX_COMPLETION_TOKENS, sent)
try:
    client.chat([], max_completion_tokens=0)
except ValueError as e:
    print(e)
"""
    result = run_python(code, OPENROUTER_MAX_COMPLETION_TOKENS="200")

    assert result.returncode == 0, result.stderr
    cap_and_sent, error = result.stdout.strip().splitlines()
    assert cap_and_sent == "200 [200, 120]"
    assert "max_completion_tokens" in error


# --- valores inválidos: falla inmediata y clara ------------------------------


@pytest.mark.parametrize(
    ("module", "env"),
    [
        ("shared.retrieval", {"RAG_MAX_COSINE_DISTANCE": "nan"}),
        ("shared.retrieval", {"RAG_MAX_COSINE_DISTANCE": "9"}),
        ("shared.retrieval", {"RAG_MAX_TOP_K": "0"}),
        ("shared.retrieval", {"RAG_MAX_TOP_K": "cuatro"}),
        ("shared.embeddings", {"EMBEDDING_BATCH_SIZE": "0"}),
        ("shared.document_limits", {"MAX_PDF_MIB": "0"}),
        ("shared.document_limits", {"CHUNK_MAX_CHARS": "abc"}),
        (
            "shared.document_limits",
            {"CHUNK_MAX_CHARS": "500", "CHUNK_OVERLAP_CHARS": "500"},
        ),
        ("loader.seed_services", {"REDIS_TTL_SECONDS": "-1"}),
    ],
)
def test_invalid_environment_values_fail_fast(
    reload_with_env: Callable[..., Any], module: str, env: dict[str, str]
) -> None:
    with pytest.raises(ValueError) as captured:
        reload_with_env(module, **env)
    assert any(name in str(captured.value) for name in env)


def test_invalid_completion_cap_fails_fast() -> None:
    result = run_python(
        "import api.openrouter_client", OPENROUTER_MAX_COMPLETION_TOKENS="0"
    )

    assert result.returncode != 0
    assert "OPENROUTER_MAX_COMPLETION_TOKENS" in result.stderr


# --- compose y .env.example --------------------------------------------------

NEW_VARIABLES = {
    "MODELO_EMBEDDING": "BAAI/bge-m3",
    "RAG_MAX_COSINE_DISTANCE": "0.55",
    "RAG_MAX_TOP_K": "4",
    "APP_PORT": "8007",
    "UPLOADER_CPUS": "2",
    "UPLOADER_MEM_LIMIT": "4g",
    "EMBEDDING_BATCH_SIZE": "4",
    "CHUNK_MAX_CHARS": "1200",
    "CHUNK_OVERLAP_CHARS": "150",
    "MAX_PDF_MIB": "50",
    "REDIS_TTL_SECONDS": "3600",
    "OPENROUTER_MAX_COMPLETION_TOKENS": "300",
    "MANUAL_BUCKET": "ceiot-manuales",
}


def test_env_example_documents_every_new_variable_with_its_default() -> None:
    lines = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in ENV_EXAMPLE.splitlines()
        if "=" in line and not line.startswith("#")
    }
    for name, default in NEW_VARIABLES.items():
        assert lines.get(name) == default, name


def test_compose_wires_each_variable_with_a_default() -> None:
    for name, default in NEW_VARIABLES.items():
        assert f"${{{name}:-{default}}}" in COMPOSE, name


@pytest.mark.parametrize(
    ("service", "names"),
    [
        (
            "loader",
            {
                "MODELO_EMBEDDING", "EMBEDDING_BATCH_SIZE", "MANUAL_BUCKET",
                "REDIS_TTL_SECONDS", "RAG_MAX_COSINE_DISTANCE", "RAG_MAX_TOP_K",
            },
        ),
        (
            "uploader",
            {
                "MODELO_EMBEDDING", "EMBEDDING_BATCH_SIZE", "MANUAL_BUCKET",
                "CHUNK_MAX_CHARS", "CHUNK_OVERLAP_CHARS", "MAX_PDF_MIB",
            },
        ),
        (
            "app",
            {
                "MODELO_EMBEDDING", "RAG_MAX_COSINE_DISTANCE", "RAG_MAX_TOP_K",
                "MAX_PDF_MIB", "CHUNK_MAX_CHARS", "CHUNK_OVERLAP_CHARS",
                "OPENROUTER_MAX_COMPLETION_TOKENS",
            },
        ),
    ],
)
def test_each_service_receives_the_variables_it_reads(
    service: str, names: set[str]
) -> None:
    block = _service(service)
    for name in names:
        assert f"{name}: ${{{name}:-{NEW_VARIABLES[name]}}}" in block, (service, name)


def test_uploader_threads_and_cpus_share_one_variable() -> None:
    block = _service("uploader")

    assert 'cpus: "${UPLOADER_CPUS:-2}"' in block
    assert 'OMP_NUM_THREADS: "${UPLOADER_CPUS:-2}"' in block
    assert "mem_limit: ${UPLOADER_MEM_LIMIT:-4g}" in block
    assert "OMP_NUM_THREADS: \"2\"" not in block


def test_app_port_is_configurable_on_the_host_side_only() -> None:
    block = _service("app")

    assert '"127.0.0.1:${APP_PORT:-8007}:8006"' in block
    assert "http://127.0.0.1:8006/health" in block


def test_manual_bucket_is_not_hardcoded_anywhere_in_compose() -> None:
    assert "MANUAL_BUCKET: ceiot-manuales" not in COMPOSE
    assert COMPOSE.count("${MANUAL_BUCKET:-ceiot-manuales}") == 2


# --- límites inyectados en la UI ----------------------------------------------


def test_served_ui_shows_default_limits_without_placeholders() -> None:
    from api import web_app

    html = web_app.render_index()

    assert "{{" not in html
    assert "Máximo 50 MiB" in html
    assert "const MAX_PDF_BYTES = 52428800;" in html
    assert 'max="4" value="4"' in html and "(1–4)" in html


def test_served_ui_reflects_configured_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import web_app

    monkeypatch.setattr(web_app, "MAX_PDF_MIB", 10)
    monkeypatch.setattr(web_app, "MAX_PDF_BYTES", 10 * 1024 * 1024)
    monkeypatch.setattr(web_app, "MAX_TOP_K", 2)
    monkeypatch.setattr(web_app, "DEFAULT_TOP_K", 2)
    html = web_app.render_index()

    assert "Máximo 10 MiB" in html and "50 MiB" not in html
    assert "const MAX_PDF_BYTES = 10485760;" in html
    assert 'max="2" value="2"' in html and "(1–2)" in html


def test_query_request_follows_configured_top_k_limit() -> None:
    code = """
from api.web_app import QueryRequest
QueryRequest(question="hola mundo", mode="rag", top_k=2)
print(QueryRequest(question="hola mundo", mode="rag").top_k)
try:
    QueryRequest(question="hola mundo", mode="rag", top_k=3)
except ValueError:
    print("rechazado")
"""
    result = run_python(code, RAG_MAX_TOP_K="2")

    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["2", "rechazado"]
