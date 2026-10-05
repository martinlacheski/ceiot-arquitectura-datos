from __future__ import annotations

import sys

import pytest  # type: ignore[import-not-found]

from loader import query_vectors  # type: ignore[import-not-found]


def test_cli_rejects_top_k_five_before_model_or_external_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["query_vectors.py", "--question", "hola", "--top-k", "5"])
    monkeypatch.setattr(
        query_vectors,
        "embedding_model",
        lambda: pytest.fail("model must not load"),
    )
    monkeypatch.setattr(
        query_vectors,
        "postgres_connection",
        lambda: pytest.fail("database must not connect"),
    )

    with pytest.raises(SystemExit, match=r"--top-k debe estar entre 1 y 4"):
        query_vectors.main()
