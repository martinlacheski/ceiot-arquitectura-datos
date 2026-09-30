"""Límites de documentos PDF configurables por entorno (defaults = práctica original)."""

from __future__ import annotations

from shared.settings import env_int  # type: ignore[import-not-found]

# El PDF se lee completo en memoria: app, uploader y parser leen el mismo valor.
MAX_PDF_MIB = env_int("MAX_PDF_MIB", 50, minimum=1, maximum=1024)
MAX_PDF_BYTES = MAX_PDF_MIB * 1024 * 1024
MAX_CHUNK_CHARS = env_int("CHUNK_MAX_CHARS", 1_200, minimum=100, maximum=20_000)
CHUNK_OVERLAP_CHARS = env_int("CHUNK_OVERLAP_CHARS", 150, minimum=0, maximum=20_000)
if CHUNK_OVERLAP_CHARS >= MAX_CHUNK_CHARS:
    raise ValueError(
        f"CHUNK_OVERLAP_CHARS={CHUNK_OVERLAP_CHARS} debe ser menor que "
        f"CHUNK_MAX_CHARS={MAX_CHUNK_CHARS}."
    )
