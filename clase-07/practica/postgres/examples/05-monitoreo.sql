-- Monitoreo (slides 54-55): qué mirar en PostgreSQL cuando "anda lento".
--
--   docker compose --env-file .env -f compose.yaml exec postgres sh -c \
--     'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /lab/examples/05-monitoreo.sql'
--
-- Se corre como dueño (ceiot), que puede ver todas las sesiones y consultas.
-- Para que la sección 4 tenga algo que mostrar, antes hacé unas preguntas en la
-- interfaz web (http://localhost:8007), por ejemplo Text-to-SQL como ana y bruno.
-- Es repetible: la tabla de práctica (lab_monitoring_demo) se crea y se borra acá.
--
-- Desde pgAdmin: abrí el archivo (Open File → carpeta examples), seleccioná un
-- bloque y ejecutalo con F5; ejecutar todo el archivo muestra sólo el último resultado,
-- los avisos (NOTICE) aparecen en la pestaña Messages. La sección 5 usa VACUUM, que no
-- puede correr dentro de un lote de varias sentencias: ejecutá esa sección sentencia por
-- sentencia (seleccionando de a una) para ver n_dead_tup antes y después.

-- === 1. Conexiones por rol y estado (pg_stat_activity) ===
-- Qué observar: cuántas sesiones tiene cada rol y cuántas están "idle in transaction"
-- (una transacción abierta sin actividad retiene candados y frena el autovacuum).
SELECT usename, state, count(*) AS sesiones
FROM pg_stat_activity
WHERE datname = current_database() AND backend_type = 'client backend'
GROUP BY usename, state
ORDER BY usename, state;
SELECT count(*) AS conexiones_totales, current_setting('max_connections') AS max_connections
FROM pg_stat_activity
WHERE backend_type = 'client backend';

-- === 2. Tamaños: base, tablas e hipertabla ===
-- Qué observar: pg_total_relation_size de una hipertabla sólo mira la tabla padre
-- (casi vacía); el tamaño real está en los chunks y lo da hypertable_size().
SELECT pg_size_pretty(pg_database_size(current_database())) AS tamano_base;
SELECT format('%I.%I', schemaname, relname) AS tabla,
       pg_size_pretty(pg_total_relation_size(relid)) AS tamano_total,
       n_live_tup AS filas_vivas
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 8;
SELECT pg_size_pretty(pg_total_relation_size('public.measurements')) AS measurements_solo_padre,
       pg_size_pretty(hypertable_size('public.measurements')) AS measurements_hypertable_size;

-- === 3. pg_stat_user_tables: lecturas, escrituras y mantenimiento ===
-- Qué observar: seq_scan alto con idx_scan bajo sugiere falta de índice; n_dead_tup alto
-- indica filas muertas pendientes de VACUUM; last_autovacuum dice cuándo corrió por última vez.
SELECT relname, seq_scan, idx_scan, n_live_tup, n_dead_tup, last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY seq_scan + coalesce(idx_scan, 0) DESC
LIMIT 8;

-- === 4. pg_stat_statements: las 10 consultas que más tiempo consumen ===
-- Qué observar: calls, total_exec_time y mean_exec_time por consulta normalizada ($1, $2 en
-- lugar de los valores). Las consultas del Text-to-SQL aparecen con el rol ai_readonly.
SELECT r.rolname AS rol,
       s.calls,
       round(s.total_exec_time::numeric, 1) AS total_ms,
       round(s.mean_exec_time::numeric, 2) AS promedio_ms,
       s.rows,
       left(regexp_replace(s.query, '\s+', ' ', 'g'), 80) AS query
FROM pg_stat_statements AS s
JOIN pg_roles AS r ON r.oid = s.userid
WHERE s.dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
  AND s.query NOT LIKE '%pg_stat_statements%'
ORDER BY s.total_exec_time DESC
LIMIT 10;
-- Para empezar de cero: SELECT pg_stat_statements_reset();  (como administrador)

-- === 5. Filas muertas y VACUUM ===
-- Qué observar: tras UPDATE masivo n_dead_tup sube (MVCC deja la versión vieja de cada fila);
-- VACUUM las recupera y n_dead_tup vuelve a 0. Las estadísticas se publican con retraso:
-- por eso se fuerza el volcado con pg_stat_force_next_flush().
DROP TABLE IF EXISTS lab_monitoring_demo;
CREATE TABLE lab_monitoring_demo AS
SELECT g AS id, md5(g::text) AS texto FROM generate_series(1, 200000) AS g;
ALTER TABLE lab_monitoring_demo ADD PRIMARY KEY (id);
-- Sin autovacuum en esta tabla para que el demo sea determinista.
ALTER TABLE lab_monitoring_demo SET (autovacuum_enabled = false);
UPDATE lab_monitoring_demo SET texto = upper(texto);
SELECT pg_stat_force_next_flush();
SELECT pg_sleep(1);
SELECT relname, n_live_tup, n_dead_tup FROM pg_stat_user_tables WHERE relname = 'lab_monitoring_demo';
-- --> VACUUM (VERBOSE, ANALYZE): fijate en "tuples: ... removed" y "dead item identifiers".
VACUUM (VERBOSE, ANALYZE) lab_monitoring_demo;
SELECT pg_stat_force_next_flush();
SELECT pg_sleep(1);
SELECT relname, n_live_tup, n_dead_tup FROM pg_stat_user_tables WHERE relname = 'lab_monitoring_demo';

-- === 6. EXPLAIN ANALYZE: sin índice vs con índice ===
-- Qué observar: sin índice, "Seq Scan" lee toda la tabla y descarta casi todo ("Rows Removed by
-- Filter"); con índice, "Index Scan" va directo a la fila. Mirá Execution Time y Buffers.
-- --> Sin índice:
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING ON)
SELECT * FROM lab_monitoring_demo WHERE texto = upper(md5('123456'));
CREATE INDEX lab_monitoring_demo_texto_idx ON lab_monitoring_demo (texto);
ANALYZE lab_monitoring_demo;
-- --> Con índice:
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING ON)
SELECT * FROM lab_monitoring_demo WHERE texto = upper(md5('123456'));

DROP TABLE lab_monitoring_demo;
-- Fin. La tabla de práctica ya fue borrada. En pgAdmin: Dashboard y Statistics muestran lo mismo.
