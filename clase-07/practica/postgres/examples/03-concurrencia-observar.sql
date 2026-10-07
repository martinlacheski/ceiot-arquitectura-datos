-- Concurrencia (slides 40-47): PESTAÑA C, el observador (PASO 8).
--
-- Se corre como dueño (ceiot) para poder ver las sesiones de otros roles. Ejecutalo
-- MIENTRAS la pestaña B está esperando en el PASO 7 del escenario b (en una tercera
-- pestaña de Query Tool, sin SET ROLE: no ejecutes el PASO 0 de A o B acá).
--
-- Desde pgAdmin: abrí el archivo (Open File → Shared Storage → examples), seleccioná un
-- bloque y ejecutalo con F5; ejecutar todo el archivo muestra sólo el último resultado.
-- Ejecutá cada consulta por separado para ver las tres. Para repetirla, volvé a apretar F5.
-- En pgAdmin: ceiot_class7 > Dashboard > "Sessions" y "Locks" muestran lo mismo.
--
-- Desde psql (con -v ON_ERROR_STOP=1 -f, imprime las tres consultas seguidas):
--   docker compose --env-file .env -f compose.yaml exec postgres sh -c \
--     'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /lab/examples/03-concurrencia-observar.sql'

-- === 1. Sesiones con transacción o consulta en curso (pg_stat_activity) ===
-- Qué observar: una sesión "active" con wait_event_type = Lock (la de B, esperando)
-- y otra "idle in transaction" (la de A: tiene la transacción abierta y no hace nada).
-- usename dice ceiot en ambas: SET ROLE app_iot cambia current_user, no el usuario de la sesión.
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

-- === 2. Quién bloquea a quién (pg_blocking_pids) ===
-- Qué observar: pid_bloqueado es la sesión de B; bloqueada_por es el pid de A.
SELECT a.pid AS pid_bloqueado,
       pg_blocking_pids(a.pid) AS bloqueada_por,
       a.wait_event_type,
       left(a.query, 70) AS query_que_espera
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0;

-- === 3. Candados de fila/transacción (pg_locks) ===
-- Qué observar: granted = f en un ShareLock de tipo transactionid: B espera que
-- termine la transacción de A (que tiene su ExclusiveLock concedido). El candado
-- "tuple" es la cola de espera por la fila.
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

-- Si las tres consultas salen vacías, B no está esperando todavía (paso 7) o ya terminó.
