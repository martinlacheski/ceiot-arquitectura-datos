\set ON_ERROR_STOP on

-- La consulta nativa usa como referencia un embedding real ya indexado.
-- Así se observa <=> directamente en psql, sin fabricar un vector de ejemplo.
WITH query_embedding AS (
    SELECT embedding
    FROM manual_chunks
    WHERE document_id = 'air-quality-pro-manual'
      AND version = 1
      AND section = 'Ajuste de referencia'
)
SELECT
    chunk.document_id,
    chunk.version,
    chunk.page,
    chunk.section,
    chunk.chunk_index,
    chunk.object_key,
    chunk.embedding <=> query_embedding.embedding AS cosine_distance,
    chunk.content
FROM manual_chunks AS chunk
CROSS JOIN query_embedding
ORDER BY chunk.embedding <=> query_embedding.embedding
LIMIT 4;

-- Esta paráfrasis no aparece literalmente en el PDF: ILIKE no hace búsqueda semántica.
SELECT
    document_id,
    version,
    page,
    section,
    chunk_index,
    object_key,
    content
FROM manual_chunks
WHERE content ILIKE '%¿Qué debo hacer si el CO2 está desviado?%'
ORDER BY document_id, version, chunk_index
LIMIT 4;
