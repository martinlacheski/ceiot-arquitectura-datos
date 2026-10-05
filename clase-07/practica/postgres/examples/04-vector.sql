\set ON_ERROR_STOP on

-- Este ejemplo trabaja sobre los PDF que cargues desde la interfaz web: no hay
-- documentos de ejemplo versionados. Si todavía no cargaste ninguno, las
-- consultas devuelven 0 filas y el aviso de abajo lo indica.
SELECT count(*) AS indexed_chunks,
       CASE WHEN count(*) = 0
            THEN 'No hay fragmentos: cargá un PDF desde la interfaz web (http://127.0.0.1:8007) y volvé a ejecutar este script.'
            ELSE 'Hay fragmentos indexados: las consultas siguientes usan el primero como referencia.'
       END AS note
FROM manual_chunks;

-- La consulta nativa usa como referencia un embedding real ya indexado (el
-- primer fragmento de cualquier documento cargado). Así se observa <=>
-- directamente en psql, sin fabricar un vector de ejemplo.
WITH query_embedding AS (
    SELECT embedding
    FROM manual_chunks
    ORDER BY document_id, version, chunk_index
    LIMIT 1
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

-- ILIKE sólo encuentra coincidencias literales: una paráfrasis de la pregunta
-- casi nunca aparece tal cual en el PDF, a diferencia de la búsqueda vectorial.
SELECT
    document_id,
    version,
    page,
    section,
    chunk_index,
    object_key,
    content
FROM manual_chunks
WHERE content ILIKE '%¿Cómo debo recalibrar el sensor después de cambiar la batería?%'
ORDER BY document_id, version, chunk_index
LIMIT 4;
