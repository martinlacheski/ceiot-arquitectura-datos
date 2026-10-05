"""Usuarios simulados y su tenant: el backend decide la organización, nunca el cliente."""

from __future__ import annotations

import pytest  # type: ignore[import-not-found]
from fastapi.testclient import TestClient  # type: ignore[import-not-found]

from api import web_app, workflows  # type: ignore[import-not-found]
from shared import tenants  # type: ignore[import-not-found]


def test_simulated_users_map_to_their_organization() -> None:
    ana = tenants.resolve_user("ana")
    bruno = tenants.resolve_user("bruno")

    assert (ana.organization_id, ana.label) == (1, "Ana — Organización A")
    assert (bruno.organization_id, bruno.label) == (2, "Bruno — Organización B")


@pytest.mark.parametrize("user_id", ["", "root", "ANA", "1", "ana; DROP TABLE x", None, 1])
def test_unknown_users_are_rejected(user_id: object) -> None:
    with pytest.raises(ValueError):
        tenants.resolve_user(user_id)  # type: ignore[arg-type]


def test_user_listing_exposes_only_id_and_label() -> None:
    users = tenants.list_users()

    assert users[0] == {"id": "ana", "label": "Ana — Organización A"}
    assert all(set(user) == {"id", "label"} for user in users)


def test_users_endpoint_returns_the_listing_without_tenant_ids() -> None:
    response = TestClient(web_app.app).get("/api/users")

    assert response.status_code == 200
    assert response.json() == tenants.list_users()
    assert "organization_id" not in response.text


# --- validación de la petición -------------------------------------------------


def _post(body: dict[str, object]):  # type: ignore[no-untyped-def]
    return TestClient(web_app.app).post("/api/query", json=body)


def test_query_requires_a_user_id() -> None:
    assert _post({"question": "¿Cuántos equipos hay?", "mode": "text-to-sql"}).status_code == 422


def test_query_rejects_an_unknown_user_id() -> None:
    response = _post(
        {"question": "¿Cuántos equipos hay?", "mode": "text-to-sql", "user_id": "mallory"}
    )

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["organization_id", "tenant_id"])
def test_query_never_accepts_a_tenant_from_the_client(field: str) -> None:
    response = _post(
        {
            "question": "¿Cuántos equipos hay?",
            "mode": "text-to-sql",
            "user_id": "ana",
            field: 2,
        }
    )

    assert response.status_code == 422


def test_query_passes_the_tenant_resolved_by_the_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[object] = []

    def fake(question: str, top_k: int, *, tenant: object) -> dict[str, object]:
        seen.append(tenant)
        return {"answer": "ok", "sql": None, "rows": [], "sources": [], "trace": ["x"]}

    monkeypatch.setitem(workflows.WORKFLOWS, "text-to-sql", fake)
    response = _post(
        {"question": "¿Cuántos equipos hay?", "mode": "text-to-sql", "user_id": "bruno"}
    )

    assert response.status_code == 200
    assert seen == [tenants.resolve_user("bruno")]
    assert response.json()["user"] == {"id": "bruno", "label": "Bruno — Organización B"}
