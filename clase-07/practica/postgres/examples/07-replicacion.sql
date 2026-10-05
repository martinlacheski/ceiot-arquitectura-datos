\set ON_ERROR_STOP on

-- Replicación por streaming: vista desde el PRIMARIO (slides 56-58).
--
-- Se corre sobre el servicio postgres, con la réplica levantada:
--   docker compose --env-file .env -f compose.yaml --profile replica up -d --wait
--   docker compose --env-file .env -f compose.yaml exec postgres sh -c \
--     'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /lab/examples/07-replicacion.sql'
-- El recorrido completo (réplica, lag, replica no es backup) está en
-- examples/07-replicacion.sh; este archivo es sólo la parte de lectura.

\echo
\echo '=== a. Quién está replicando: pg_stat_replication ==='
\echo 'Qué observar: una fila (walreceiver, el proceso de la réplica) con state = streaming. sent_lsn es lo que el primario envió,'
\echo 'replay_lsn lo que la réplica ya aplicó; replay_lag es el retraso medido por el tiempo.'
SELECT application_name, client_addr, state, sync_state,
       sent_lsn, replay_lsn, replay_lag
FROM pg_stat_replication;

\echo
\echo '=== b. Slot de replicación: pg_replication_slots ==='
\echo 'Qué observar: replica_1 está active. El slot obliga al primario a conservar el WAL que la'
\echo 'réplica todavía no leyó; retained_wal crece si la réplica se cae (por eso max_slot_wal_keep_size).'
SELECT slot_name, slot_type, active, wal_status,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal
FROM pg_replication_slots;

\echo
\echo '=== c. Retraso en bytes: cuánto WAL le falta aplicar a la réplica ==='
\echo 'Con la réplica al día debe dar cerca de 0 bytes.'
SELECT application_name,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS lag_bytes
FROM pg_stat_replication;
