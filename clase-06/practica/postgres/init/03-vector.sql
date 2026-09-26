\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS manual_chunks (
    document_id text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    page integer NOT NULL CHECK (page > 0),
    section text NOT NULL CHECK (btrim(section) <> ''),
    content text NOT NULL CHECK (btrim(content) <> ''),
    object_key text NOT NULL,
    embedding_model text NOT NULL,
    embedding vector(384) NOT NULL,
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    indexed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, version, chunk_index),
    CONSTRAINT manual_chunks_document_fk
        FOREIGN KEY (document_id, version)
        REFERENCES manual_documents (document_id, version),
    CONSTRAINT manual_chunks_object_fk
        FOREIGN KEY (object_key)
        REFERENCES manual_documents (object_key),
    CONSTRAINT manual_chunks_embedding_dimensions
        CHECK (vector_dims(embedding) = 384)
);

CREATE INDEX IF NOT EXISTS manual_chunks_document_idx
    ON manual_chunks (document_id, version, page, chunk_index);
