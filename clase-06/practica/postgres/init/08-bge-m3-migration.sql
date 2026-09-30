\set ON_ERROR_STOP on

-- Evolución idempotente que migra los embeddings existentes del laboratorio
-- de intfloat/multilingual-e5-small (384 dimensiones) a BAAI/bge-m3
-- (1024 dimensiones). Un vector de 384 dimensiones no puede reescalarse ni
-- reinterpretarse como uno de 1024: esta migración descarta los chunks
-- obsoletos y deja los documentos afectados en estado 'pending' para que se
-- reindexen con el modelo nuevo (el manual semilla con
-- `python -m loader.ingest_vectors`; los PDF cargados por la UI con
-- `python -m loader.reindex_documents`, ver README sección 5).
--
-- Es segura de reaplicar: si la columna ya es vector(1024) no hace nada, y
-- nunca descarta chunks que ya estén en 1024 dimensiones.
BEGIN;

DO $migration$
DECLARE
    current_type text;
BEGIN
    SELECT format_type(attribute.atttypid, attribute.atttypmod)
    INTO current_type
    FROM pg_catalog.pg_attribute AS attribute
    WHERE attribute.attrelid = 'public.manual_chunks'::regclass
      AND attribute.attname = 'embedding';

    IF current_type = 'vector(1024)' THEN
        RAISE NOTICE 'manual_chunks.embedding ya es vector(1024); nada que migrar.';
        RETURN;
    END IF;

    -- Los vectores de 384 dimensiones (multilingual-e5-small) son
    -- incompatibles con bge-m3: se descartan, nunca se reescalan.
    DELETE FROM public.manual_chunks;

    -- Los documentos afectados vuelven a 'pending' respetando
    -- manual_documents_indexed_metadata_check (chunk_count > 0 y
    -- embedding_model no vacío sólo se exigen cuando index_status = 'indexed').
    UPDATE public.manual_documents
    SET chunk_count = 0,
        embedding_model = NULL,
        index_status = 'pending'
    WHERE index_status = 'indexed';

    ALTER TABLE public.manual_chunks
        DROP CONSTRAINT IF EXISTS manual_chunks_embedding_dimensions;

    ALTER TABLE public.manual_chunks
        ALTER COLUMN embedding TYPE vector(1024);

    ALTER TABLE public.manual_chunks
        ADD CONSTRAINT manual_chunks_embedding_dimensions
        CHECK (vector_dims(embedding) = 1024);

    RAISE NOTICE 'manual_chunks.embedding migrado a vector(1024); documentos afectados vueltos a pending.';
END
$migration$;

COMMIT;
