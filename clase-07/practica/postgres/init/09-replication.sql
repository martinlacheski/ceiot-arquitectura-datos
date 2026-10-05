\set ON_ERROR_STOP on

-- Rol para la réplica de streaming (clase 7, slides 56-58).
--
-- REPLICATION permite abrir conexiones de replicación (pg_basebackup y el envío
-- continuo de WAL) y nada más: no es superusuario, no lee tablas y no escribe.
-- La contraseña es fija sólo para esta demo local: no reutilizar en producción.
--
-- La regla de pg_hba.conf que deja entrar a este rol desde la red está en
-- postgres/pg_hba.conf (montado con hba_file en compose.yaml).
--
-- Este archivo corre solo al crear el volumen. Sobre un volumen ya existente:
--   docker compose --env-file .env -f compose.yaml exec postgres sh -c \
--     'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/09-replication.sql'
-- Se puede volver a aplicar: crea el rol si falta y siempre deja sus atributos.
SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'replicator') AS crear \gset
\if :crear
    CREATE ROLE replicator LOGIN REPLICATION PASSWORD 'ceiot_replicator_local_only';
\endif
ALTER ROLE replicator LOGIN REPLICATION NOSUPERUSER PASSWORD 'ceiot_replicator_local_only';
