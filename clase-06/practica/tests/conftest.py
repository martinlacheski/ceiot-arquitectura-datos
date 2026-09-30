"""Shared test isolation."""

from collections.abc import Iterator

import pytest

from shared import sql_schema  # type: ignore[import-not-found]


@pytest.fixture(autouse=True)
def _isolate_sql_schema_cache() -> Iterator[None]:
    # The schema prompt is cached per process; never let one test leak it into another.
    sql_schema.clear_cache()
    yield
    sql_schema.clear_cache()
