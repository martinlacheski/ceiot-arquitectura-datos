\set ON_ERROR_STOP on
\pset pager off
\x off

-- Concurrencia (slides 40-47): TERMINAL C, el observador (paso 8).
--
-- Se corre como dueño (ceiot) para poder ver las sesiones de otros roles. Ejecutalo
-- MIENTRAS la terminal B está esperando en el paso 7 del escenario b:
--
--   docker compose --env-file .env -f compose.yaml exec postgres sh -c \
--     'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /lab/examples/03-concurrencia-observar.sql'
--
-- Para repetir la consulta cada 2 segundos en una sesión interactiva de psql:
--   \i /lab/examples/03-concurrencia-observar.sql   y luego   \watch 2  (sobre una consulta)
-- En pgAdmin: ceiot_class7 > Dashboard > "Sessions" y "Locks" muestran lo mismo.

\echo
\echo '=== 1. Sesiones con transacción o consulta en curso (pg_stat_activity) ==='
\echo 'Qué observar: una sesión "active" con wait_event_type = Lock (la de B, esperando)'
\echo 'y otra "idle in transaction" (la de A: tiene la transacción abierta y no hace nada).'
\echo 'usename dice ceiot en ambas: SET ROLE app_iot cambia current_user, no el usuario de la sesión.'
SELECT pid,
       usename,
       state,
       wait_event_type,
       wait_event,
       now() - xact_start AS transaccion_abierta_hace,
       left(query, 70) AS query
FROM pg_stat_activity
WHERE datname = current_database()
  AND backend_type = 'client backend'
  AND pid <> pg_backend_pid()
  AND state IS DISTINCT FROM 'idle'
ORDER BY xact_start;

\echo
\echo '=== 2. Quién bloquea a quién (pg_blocking_pids) ==='
\echo 'Qué observar: pid_bloqueado es la sesión de B; bloqueada_por es el pid de A.'
SELECT a.pid AS pid_bloqueado,
       pg_blocking_pids(a.pid) AS bloqueada_por,
       a.wait_event_type,
       left(a.query, 70) AS query_que_espera
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0;

\echo
\echo '=== 3. Candados de fila/transacción (pg_locks) ==='
\echo 'Qué observar: granted = f en un ShareLock de tipo transactionid: B espera que'
\echo 'termine la transacción de A (que tiene su ExclusiveLock concedido). El candado'
\echo '"tuple" es la cola de espera por la fila.'
SELECT l.pid,
       l.locktype,
       l.mode,
       l.granted,
       l.relation::regclass AS tabla,
       l.transactionid,
       a.usename
FROM pg_locks AS l
JOIN pg_stat_activity AS a USING (pid)
WHERE a.datname = current_database()
  AND a.pid <> pg_backend_pid()
  AND l.locktype IN ('tuple', 'transactionid')
ORDER BY l.granted, l.pid, l.locktype;

\echo
\echo 'Si las tres consultas salen vacías, B no está esperando todavía (paso 7) o ya terminó.'
