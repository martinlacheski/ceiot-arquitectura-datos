from __future__ import annotations

import os

import psycopg  # type: ignore[import-not-found]


def _owner_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "ceiot_class6"),
        user=os.getenv("POSTGRES_USER", "ceiot"),
        password=os.environ["POSTGRES_PASSWORD"],
        autocommit=True,
    )


def test_document_upload_columns_and_constraints_are_installed() -> None:
    with _owner_connection() as connection:
        columns = dict(
            connection.execute(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'manual_documents'
                  AND column_name IN (
                      'sha256', 'byte_count', 'page_count', 'chunk_count',
                      'embedding_model', 'index_status'
                  )
                """
            ).fetchall()
        )
        assert columns == {
            "sha256": "YES",
            "byte_count": "YES",
            "page_count": "YES",
            "chunk_count": "NO",
            "embedding_model": "YES",
            "index_status": "NO",
        }

        constraints = dict(
            connection.execute(
                """
                SELECT conname, pg_catalog.pg_get_constraintdef(oid)
                FROM pg_catalog.pg_constraint
                WHERE conrelid IN (
                    'public.manual_documents'::regclass,
                    'public.manual_chunks'::regclass
                )
                  AND conname IN (
                      'manual_documents_chunk_count_check',
                      'manual_documents_index_status_check',
                      'manual_documents_sha256_format_check',
                      'manual_documents_byte_count_range_check',
                      'manual_documents_page_count_range_check',
                      'manual_documents_chunk_count_range_check',
                      'manual_documents_indexed_metadata_check',
                      'manual_documents_upload_metadata_required_check',
                      'manual_documents_identity_object_key_key',
                      'manual_chunks_document_fk',
                      'manual_chunks_object_fk',
                      'manual_chunks_document_object_fk'
                  )
                """
            ).fetchall()
        )

    assert set(constraints) == {
        "manual_documents_chunk_count_check",
        "manual_documents_index_status_check",
        "manual_documents_sha256_format_check",
        "manual_documents_byte_count_range_check",
        "manual_documents_page_count_range_check",
        "manual_documents_chunk_count_range_check",
        "manual_documents_indexed_metadata_check",
        "manual_documents_upload_metadata_required_check",
        "manual_documents_identity_object_key_key",
        "manual_chunks_document_fk",
        "manual_chunks_object_fk",
        "manual_chunks_document_object_fk",
    }
    assert "^[0-9a-f]{64}$" in constraints[
        "manual_documents_sha256_format_check"
    ]
    byte_count_constraint = constraints[
        "manual_documents_byte_count_range_check"
    ]
    assert "byte_count >= 1" in byte_count_constraint
    assert "byte_count <= 10485760" in byte_count_constraint
    page_count_constraint = constraints[
        "manual_documents_page_count_range_check"
    ]
    assert "page_count >= 1" in page_count_constraint
    assert "page_count <= 20" in page_count_constraint
    chunk_count_constraint = constraints[
        "manual_documents_chunk_count_range_check"
    ]
    assert "chunk_count >= 0" in chunk_count_constraint
    assert "chunk_count <= 120" in chunk_count_constraint
    assert "chunk_count > 0" in constraints[
        "manual_documents_indexed_metadata_check"
    ]
    assert "btrim(embedding_model)" in constraints[
        "manual_documents_indexed_metadata_check"
    ]
    upload_metadata_constraint = constraints[
        "manual_documents_upload_metadata_required_check"
    ]
    assert "upload-" in upload_metadata_constraint
    assert "sha256 IS NOT NULL" in upload_metadata_constraint
    assert "byte_count IS NOT NULL" in upload_metadata_constraint
    assert "page_count IS NOT NULL" in upload_metadata_constraint
    assert "UNIQUE (document_id, version, object_key)" in constraints[
        "manual_documents_identity_object_key_key"
    ]
    assert "FOREIGN KEY (document_id, version, object_key)" in constraints[
        "manual_chunks_document_object_fk"
    ]
    assert "REFERENCES manual_documents(document_id, version, object_key)" in constraints[
        "manual_chunks_document_object_fk"
    ]


def test_rag_ingest_has_only_bounded_catalog_privileges() -> None:
    with _owner_connection() as connection:
        role = connection.execute(
            """
            SELECT
                rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                rolinherit, rolreplication, rolbypassrls
            FROM pg_catalog.pg_roles
            WHERE rolname = 'rag_ingest'
            """
        ).fetchone()
        privileges = connection.execute(
            """
            SELECT
                has_database_privilege('rag_ingest', current_database(), 'CONNECT'),
                has_database_privilege('rag_ingest', current_database(), 'CREATE'),
                has_database_privilege('rag_ingest', current_database(), 'TEMPORARY'),
                has_schema_privilege('rag_ingest', 'public', 'USAGE'),
                has_schema_privilege('rag_ingest', 'public', 'CREATE'),
                has_schema_privilege('rag_ingest', 'lab_read', 'USAGE'),
                has_table_privilege('rag_ingest', 'public.manual_documents', 'SELECT'),
                has_table_privilege('rag_ingest', 'public.manual_documents', 'INSERT'),
                has_table_privilege('rag_ingest', 'public.manual_documents', 'UPDATE'),
                has_table_privilege('rag_ingest', 'public.manual_documents', 'DELETE'),
                has_table_privilege('rag_ingest', 'public.manual_chunks', 'SELECT'),
                has_table_privilege('rag_ingest', 'public.manual_chunks', 'INSERT'),
                has_table_privilege('rag_ingest', 'public.manual_chunks', 'UPDATE'),
                has_table_privilege('rag_ingest', 'public.manual_chunks', 'DELETE'),
                has_table_privilege('rag_ingest', 'public.devices', 'SELECT'),
                has_table_privilege('rag_ingest', 'public.measurements', 'SELECT'),
                has_table_privilege('rag_ingest', 'lab_read.devices', 'SELECT'),
                has_table_privilege('rag_ingest', 'lab_read.measurements', 'SELECT')
            """
        ).fetchone()
        settings = set(
            connection.execute(
                """
                SELECT unnest(setting.setconfig)
                FROM pg_catalog.pg_db_role_setting AS setting
                JOIN pg_catalog.pg_roles AS role
                  ON role.oid = setting.setrole
                WHERE role.rolname = 'rag_ingest'
                  AND setting.setdatabase = 0
                """
            ).fetchall()
        )

    assert role == (True, False, False, False, False, False, False)
    assert privileges == (
        True,
        False,
        False,
        True,
        False,
        False,
        True,
        True,
        True,
        False,
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
    )
    assert settings == {
        ("search_path=public, pg_catalog",),
        ("statement_timeout=10000ms",),
        ("lock_timeout=2000ms",),
        ("idle_in_transaction_session_timeout=5000ms",),
    }


def test_seeded_manual_metadata_matches_its_stored_chunks() -> None:
    with _owner_connection() as connection:
        observed = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM public.locations),
                (SELECT count(*) FROM public.devices),
                -- El total global crece con el historial horario reciente de
                -- ENV-X (ver postgres/seed/01-iot.sql); sólo el día fijo
                -- 2025-05-12 permanece con un conteo exacto y estable.
                (SELECT count(*) FROM public.measurements
                 WHERE measured_at >= '2025-05-12T00:00:00Z'
                   AND measured_at < '2025-05-13T00:00:00Z'),
                (SELECT count(*) FROM public.measurements),
                (SELECT count(*)
                 FROM public.manual_documents
                 WHERE document_id = 'env-x-manual'
                   AND version = 1
                   AND storage_status = 'available'),
                document.sha256,
                document.byte_count,
                document.page_count,
                document.index_status,
                document.chunk_count,
                document.embedding_model,
                count(chunk.*)::integer,
                count(DISTINCT chunk.embedding_model)::integer,
                min(chunk.embedding_model)
            FROM public.manual_documents AS document
            LEFT JOIN public.manual_chunks AS chunk
              ON chunk.document_id = document.document_id
             AND chunk.version = document.version
             AND chunk.object_key = document.object_key
            WHERE document.document_id = 'env-x-manual'
              AND document.version = 1
            GROUP BY
                document.document_id,
                document.version,
                document.index_status,
                document.chunk_count,
                document.embedding_model
            """
        ).fetchone()

    (
        location_count,
        device_count,
        fixed_day_measurement_count,
        total_measurement_count,
        manual_available_count,
        sha256,
        byte_count,
        page_count,
        index_status,
        chunk_count,
        embedding_model,
        chunk_join_count,
        distinct_chunk_models,
        min_chunk_model,
    ) = observed

    # Ubicaciones y dispositivos son estables: 3 ubicaciones y 4 dispositivos
    # (AIR-002, AMB-001/ENV-X, ACT-003, AMB-005/ENV-X).
    assert location_count == 3
    assert device_count == 4
    assert fixed_day_measurement_count == 8
    # El historial horario reciente de ENV-X agrega al menos 96 filas
    # (48 de temperatura + 48 de humedad); resembrar en otra hora sólo suma.
    assert total_measurement_count >= 8 + 96
    assert manual_available_count == 1
    assert (sha256, byte_count, page_count) == (None, None, None)
    assert index_status == "indexed"
    assert chunk_count == 4
    assert embedding_model == "intfloat/multilingual-e5-small"
    assert chunk_join_count == 4
    assert distinct_chunk_models == 1
    assert min_chunk_model == "intfloat/multilingual-e5-small"
