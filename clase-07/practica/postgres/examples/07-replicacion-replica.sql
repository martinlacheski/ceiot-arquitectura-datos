\set ON_ERROR_STOP on

-- Replicación por streaming: vista desde la RÉPLICA (slides 56-58).
--
-- Se corre sobre el servicio postgres-replica (modo hot standby: sólo lectura):
--   docker compose --env-file .env -f compose.yaml --profile replica exec postgres-replica sh -c \
--     'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /lab/examples/07-replicacion-replica.sql'
-- Desde el host también: psql -h 127.0.0.1 -p 5438 (puerto POSTGRES_REPLICA_PORT).

\echo
\echo '=== a. ¿Es una réplica? ==='
\echo 'Qué observar: pg_is_in_recovery() = t; replay_lsn avanza cada vez que el primario escribe.'
SELECT pg_is_in_recovery() AS en_recuperacion,
       pg_last_wal_replay_lsn() AS replay_lsn,
       pg_last_xact_replay_timestamp() AS ultima_transaccion_aplicada;

\echo
\echo '=== b. Los mismos datos que el primario (como dueño, sin RLS) ==='
SELECT (SELECT count(*) FROM devices) AS devices,
       (SELECT count(*) FROM measurements) AS measurements;

\echo
\echo '=== c. Las políticas RLS también viajaron: son parte del catálogo, que se replica ==='
SELECT count(*) AS politicas_tenant_isolation
FROM pg_policies
WHERE policyname = 'tenant_isolation';

\echo
\echo '=== d. Escribir en la réplica falla ==='
\echo 'Qué observar: "cannot execute INSERT in a read-only transaction". Las escrituras van siempre al primario.'
\set ON_ERROR_STOP off
INSERT INTO measurements (organization_id, device_id, measured_at, variable, value, unit, quality)
VALUES (1, 'AIR-002', now(), 'intento_en_replica', 0, 'x', 'GOOD');
\set ON_ERROR_STOP on
