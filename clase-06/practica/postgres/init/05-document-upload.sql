\set ON_ERROR_STOP on

-- Evolución idempotente para la ingesta de documentos del laboratorio local.
-- La contraseña fija es sólo para esta demo aislada; no es un esquema de
-- permisos apto para producción.
BEGIN;

ALTER TABLE public.manual_documents
    ADD COLUMN IF NOT EXISTS sha256 text,
    ADD COLUMN IF NOT EXISTS byte_count bigint,
    ADD COLUMN IF NOT EXISTS page_count integer,
    ADD COLUMN IF NOT EXISTS chunk_count integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS embedding_model text,
    ADD COLUMN IF NOT EXISTS index_status text NOT NULL DEFAULT 'pending';

DO $constraints$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.manual_documents'::regclass
          AND conname = 'manual_documents_chunk_count_check'
    ) THEN
        ALTER TABLE public.manual_documents
            ADD CONSTRAINT manual_documents_chunk_count_check
            CHECK (chunk_count >= 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.manual_documents'::regclass
          AND conname = 'manual_documents_index_status_check'
    ) THEN
        ALTER TABLE public.manual_documents
            ADD CONSTRAINT manual_documents_index_status_check
            CHECK (index_status IN ('pending', 'indexed', 'failed'));
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.manual_documents'::regclass
          AND conname = 'manual_documents_sha256_format_check'
    ) THEN
        ALTER TABLE public.manual_documents
            ADD CONSTRAINT manual_documents_sha256_format_check
            CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$');
    END IF;

    -- Único cap restante: 50 MiB, porque el PDF se lee completo en memoria
    -- (mismo valor que MAX_PDF_BYTES en loader/pdf_document.py). Páginas,
    -- caracteres extraídos y cantidad de chunks quedan sin límite superior:
    -- los chunks escalan con el documento.
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.manual_documents'::regclass
          AND conname = 'manual_documents_byte_count_range_check'
    ) THEN
        ALTER TABLE public.manual_documents
            ADD CONSTRAINT manual_documents_byte_count_range_check
            CHECK (byte_count IS NULL OR byte_count BETWEEN 1 AND 52428800);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.manual_documents'::regclass
          AND conname = 'manual_documents_page_count_range_check'
    ) THEN
        ALTER TABLE public.manual_documents
            ADD CONSTRAINT manual_documents_page_count_range_check
            CHECK (page_count IS NULL OR page_count >= 1);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.manual_documents'::regclass
          AND conname = 'manual_documents_chunk_count_range_check'
    ) THEN
        ALTER TABLE public.manual_documents
            ADD CONSTRAINT manual_documents_chunk_count_range_check
            CHECK (chunk_count >= 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.manual_documents'::regclass
          AND conname = 'manual_documents_indexed_metadata_check'
    ) THEN
        ALTER TABLE public.manual_documents
            ADD CONSTRAINT manual_documents_indexed_metadata_check
            CHECK (
                index_status <> 'indexed'
                OR (
                    chunk_count > 0
                    AND NULLIF(btrim(embedding_model), '') IS NOT NULL
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.manual_documents'::regclass
          AND conname = 'manual_documents_upload_metadata_required_check'
    ) THEN
        ALTER TABLE public.manual_documents
            ADD CONSTRAINT manual_documents_upload_metadata_required_check
            CHECK (
                left(document_id, 7) <> 'upload-'
                OR (
                    sha256 IS NOT NULL
                    AND byte_count IS NOT NULL
                    AND page_count IS NOT NULL
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.manual_documents'::regclass
          AND conname = 'manual_documents_identity_object_key_key'
    ) THEN
        ALTER TABLE public.manual_documents
            ADD CONSTRAINT manual_documents_identity_object_key_key
            UNIQUE (document_id, version, object_key);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.manual_chunks'::regclass
          AND conname = 'manual_chunks_document_object_fk'
    ) THEN
        ALTER TABLE public.manual_chunks
            ADD CONSTRAINT manual_chunks_document_object_fk
            FOREIGN KEY (document_id, version, object_key)
            REFERENCES public.manual_documents (document_id, version, object_key);
    END IF;
END
$constraints$;

-- Un volumen ya indexado debe reflejar los chunks que realmente conserva.
-- Los documentos sin chunks mantienen su estado (pending o failed).
WITH indexed_documents AS (
    SELECT
        document_id,
        version,
        object_key,
        count(*)::integer AS chunk_count,
        CASE
            WHEN count(DISTINCT embedding_model) = 1 THEN min(embedding_model)
            ELSE NULL
        END AS embedding_model
    FROM public.manual_chunks
    GROUP BY document_id, version, object_key
)
UPDATE public.manual_documents AS document
SET chunk_count = indexed.chunk_count,
    embedding_model = indexed.embedding_model,
    index_status = 'indexed'
FROM indexed_documents AS indexed
WHERE document.document_id = indexed.document_id
  AND document.version = indexed.version
  AND document.object_key = indexed.object_key;

DO $role$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'rag_ingest'
    ) THEN
        CREATE ROLE rag_ingest
            LOGIN
            PASSWORD 'ceiot_rag_ingest_demo_only'
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            NOREPLICATION
            NOBYPASSRLS;
    END IF;
END
$role$;

ALTER ROLE rag_ingest
    WITH LOGIN
    PASSWORD 'ceiot_rag_ingest_demo_only'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOREPLICATION
    NOBYPASSRLS;
ALTER ROLE rag_ingest SET search_path = public, pg_catalog;
ALTER ROLE rag_ingest SET statement_timeout = '10000ms';
ALTER ROLE rag_ingest SET lock_timeout = '2000ms';
ALTER ROLE rag_ingest SET idle_in_transaction_session_timeout = '5000ms';

REVOKE ALL ON SCHEMA public FROM rag_ingest;
REVOKE ALL ON SCHEMA lab_read FROM rag_ingest;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM rag_ingest;
REVOKE ALL ON ALL TABLES IN SCHEMA lab_read FROM rag_ingest;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM rag_ingest;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON TABLES FROM rag_ingest;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON SEQUENCES FROM rag_ingest;

-- Ningún rol nuevo debe adquirir escritura por privilegios globales de PUBLIC.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON ALL TABLES IN SCHEMA public FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLES FROM PUBLIC;

GRANT USAGE ON SCHEMA public TO rag_ingest;
GRANT SELECT, INSERT, UPDATE ON public.manual_documents TO rag_ingest;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.manual_chunks TO rag_ingest;

COMMIT;

SELECT format(
    'REVOKE CREATE, TEMPORARY ON DATABASE %I FROM PUBLIC',
    current_database()
) \gexec
SELECT format(
    'REVOKE CREATE, TEMPORARY ON DATABASE %I FROM rag_ingest',
    current_database()
) \gexec
SELECT format(
    'GRANT CONNECT ON DATABASE %I TO rag_ingest',
    current_database()
) \gexec
