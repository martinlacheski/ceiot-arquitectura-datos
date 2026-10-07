-- Replicación por streaming: vista desde la RÉPLICA (slides 56-58).
--
-- Se corre sobre el servicio postgres-replica (modo hot standby: sólo lectura):
--   docker compose --env-file .env -f compose.yaml --profile replica exec postgres-replica sh -c \
--     'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /lab/examples/07-replicacion-replica.sql'
-- Desde el host también: psql -h 127.0.0.1 -p 5438 (puerto POSTGRES_REPLICA_PORT).
--
-- Desde pgAdmin: abrí el archivo (Open File → carpeta examples), seleccioná un
-- bloque y ejecutalo con F5; ejecutar todo el archivo muestra sólo el último resultado,
-- los avisos (NOTICE) aparecen en la pestaña Messages.
-- (En pgAdmin conectate al servidor de la réplica, puerto POSTGRES_REPLICA_PORT.)

-- === a. ¿Es una réplica? ===
-- Qué observar: pg_is_in_recovery() = t; replay_lsn avanza cada vez que el primario escribe.
SELECT pg_is_in_recovery() AS en_recuperacion,
       pg_last_wal_replay_lsn() AS replay_lsn,
       pg_last_xact_replay_timestamp() AS ultima_transaccion_aplicada;

-- === b. Los mismos datos que el primario (como dueño, sin RLS) ===
SELECT (SELECT count(*) FROM devices) AS devices,
       (SELECT count(*) FROM measurements) AS measurements;

-- === c. Las políticas RLS también viajaron: son parte del catálogo, que se replica ===
SELECT count(*) AS politicas_tenant_isolation
FROM pg_policies
WHERE policyname = 'tenant_isolation';

-- === d. Escribir en la réplica falla ===
-- Qué observar: el aviso "Rechazado:" con "cannot execute INSERT in a read-only transaction".
-- Las escrituras van siempre al primario. El error se captura para que el script no se corte.
DO $$
BEGIN
    INSERT INTO measurements (organization_id, device_id, measured_at, variable, value, unit, quality)
    VALUES (1, 'AIR-002', now(), 'intento_en_replica', 0, 'x', 'GOOD');
    RAISE NOTICE 'ATENCIÓN: la réplica no debería aceptar escrituras';
EXCEPTION WHEN others THEN
    RAISE NOTICE 'Rechazado: %', SQLERRM;
END $$;
