from app.main import app


def test_health_is_unprefixed_and_resources_remain_under_api() -> None:
    routes = {getattr(route, "path") for route in app.routes if hasattr(route, "path")}

    assert "/health" in routes
    assert "/api/health" not in routes
    assert "/api/organizations" in routes
    assert "/api/locations" in routes
    assert "/api/devices" in routes
    assert "/api/measurements" in routes
