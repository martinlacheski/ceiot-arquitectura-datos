-- Particionamiento (slides 60-64): tabla particionada por rango de fechas vs
-- tabla común, y comparación con los chunks de TimescaleDB.
--
--   docker compose --env-file .env -f compose.yaml exec postgres sh -c \
--     'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /lab/examples/06-particionamiento.sql'
--
-- Crea el esquema lab_ops (sólo del dueño ceiot: ningún rol de aplicación tiene
-- permisos, así que el Text-to-SQL no lo ve) con ~2,6 millones de filas sintéticas
-- en dos tablas con los mismos datos. Tarda alrededor de 30 segundos.
-- Es repetible: empieza borrando el esquema. Las tablas quedan creadas para que
-- las explores en pgAdmin (ceiot_class7 > Schemas > lab_ops > Tables); la
-- limpieza está en la última línea del archivo.
--
-- Desde pgAdmin: abrí el archivo (Open File → Shared Storage → examples), seleccioná un
-- bloque y ejecutalo con F5; ejecutar todo el archivo muestra sólo el último resultado,
-- los avisos (NOTICE) aparecen en la pestaña Messages. Los tiempos de carga y de retención
-- se informan como avisos (NOTICE) con clock_timestamp(). VACUUM no puede correr dentro de
-- un lote de varias sentencias: ejecutá la sección 4 sentencia por sentencia.

DROP SCHEMA IF EXISTS lab_ops CASCADE;
CREATE SCHEMA lab_ops;

-- === 1. Dos tablas con los mismos datos: particionada por mes y común ===
-- Qué observar: measurements_archive tiene 12 particiones (una por mes de 2025).
-- measurements_flat es una sola tabla. Ambas reciben las mismas 2.628.000 filas.

CREATE TABLE lab_ops.measurements_flat (
    organization_id bigint NOT NULL,
    device_id       text NOT NULL,
    measured_at     timestamptz NOT NULL,
    variable        text NOT NULL,
    value           numeric(12, 3) NOT NULL
) WITH (autovacuum_enabled = false);
-- autovacuum desactivado sólo aquí, para que el paso 4 muestre filas muertas
-- de forma determinista; en producción no se hace.

CREATE TABLE lab_ops.measurements_archive (
    organization_id bigint NOT NULL,
    device_id       text NOT NULL,
    measured_at     timestamptz NOT NULL,
    variable        text NOT NULL,
    value           numeric(12, 3) NOT NULL
) PARTITION BY RANGE (measured_at);

-- Una partición por mes de 2025: límite inferior inclusivo, superior exclusivo.
DO $partitions$
DECLARE
    mes date;
BEGIN
    FOR mes IN SELECT generate_series(date '2025-01-01', date '2025-12-01', interval '1 month')::date
    LOOP
        EXECUTE format(
            'CREATE TABLE lab_ops.measurements_archive_%s PARTITION OF lab_ops.measurements_archive
             FOR VALUES FROM (%L) TO (%L)',
            to_char(mes, 'YYYY_MM'),
            mes::timestamptz,
            (mes + interval '1 month')::timestamptz
        );
    END LOOP;
END
$partitions$;

-- Una medición cada 12 segundos durante todo 2025, repartida entre 8 equipos
-- sintéticos de 2 organizaciones. Determinista: sin random().
-- Los tiempos de carga y de índices aparecen como avisos (NOTICE; pestaña Messages en pgAdmin).
DO $timing$
DECLARE
    t0 timestamptz;
BEGIN
    t0 := clock_timestamp();
    INSERT INTO lab_ops.measurements_flat
    SELECT CASE WHEN g % 8 < 4 THEN 1 ELSE 2 END,
           'SIM-' || (g % 8 + 1),
           timestamptz '2025-01-01 00:00:00+00' + g * interval '12 seconds',
           (ARRAY['temperature', 'humidity', 'co2'])[g % 3 + 1],
           round((20 + 10 * sin(g / 5000.0) + g % 7)::numeric, 3)
    FROM generate_series(0, 2627999) AS g;
    RAISE NOTICE 'Carga de measurements_flat: % ms', round(extract(epoch FROM clock_timestamp() - t0) * 1000);

    -- Mismos datos en la tabla particionada: cada fila va sola a su partición.
    t0 := clock_timestamp();
    INSERT INTO lab_ops.measurements_archive SELECT * FROM lab_ops.measurements_flat;
    RAISE NOTICE 'Carga de measurements_archive: % ms', round(extract(epoch FROM clock_timestamp() - t0) * 1000);

    -- Ahora los índices (misma columna en ambas):
    t0 := clock_timestamp();
    CREATE INDEX measurements_flat_measured_at_idx ON lab_ops.measurements_flat (measured_at);
    RAISE NOTICE 'Índice en measurements_flat: % ms', round(extract(epoch FROM clock_timestamp() - t0) * 1000);

    -- En la tabla particionada el índice se declara una vez y PostgreSQL crea uno por partición.
    t0 := clock_timestamp();
    CREATE INDEX measurements_archive_measured_at_idx ON lab_ops.measurements_archive (measured_at);
    RAISE NOTICE 'Índice en measurements_archive: % ms', round(extract(epoch FROM clock_timestamp() - t0) * 1000);
END
$timing$;
ANALYZE lab_ops.measurements_flat;
ANALYZE lab_ops.measurements_archive;

-- === 2. Consulta de UN mes: poda de particiones (partition pruning) ===
-- Qué observar: en measurements_archive el plan sólo toca measurements_archive_2025_06;
-- las otras 11 particiones ni aparecen. En measurements_flat el plan recorre una tabla
-- o un índice de 2,6 millones de filas. Compará "Buffers" y "Execution Time".
-- Ojo: con una sola consulta los tiempos pueden ser parecidos (el índice ya ayuda a la tabla
-- común, y acá los datos están ordenados por fecha). La ventaja fuerte de particionar aparece
-- en la retención y el mantenimiento (paso 4), no en esta consulta aislada.
-- --> Particionada:
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT variable, count(*), round(avg(value), 2)
FROM lab_ops.measurements_archive
WHERE measured_at >= '2025-06-01' AND measured_at < '2025-07-01'
GROUP BY variable;
-- --> Común:
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT variable, count(*), round(avg(value), 2)
FROM lab_ops.measurements_flat
WHERE measured_at >= '2025-06-01' AND measured_at < '2025-07-01'
GROUP BY variable;

-- === 3. Particiones, filas y tamaños ===
-- Qué observar: 12 particiones de tamaño parecido. Abrí el árbol en pgAdmin para verlas.
SELECT c.relname AS particion,
       pt.level,
       (SELECT count(*) FROM lab_ops.measurements_archive a WHERE a.tableoid = pt.relid) AS filas,
       pg_size_pretty(pg_total_relation_size(pt.relid)) AS tamano,
       pg_get_expr(c.relpartbound, c.oid) AS rango
FROM pg_partition_tree('lab_ops.measurements_archive') AS pt
JOIN pg_class AS c ON c.oid = pt.relid
WHERE pt.isleaf
ORDER BY c.relname;
-- La tabla padre particionada no almacena nada: su tamaño es la suma de las hojas.
SELECT pg_size_pretty(sum(pg_total_relation_size(relid))) AS archive_total_particiones,
       pg_size_pretty(pg_total_relation_size('lab_ops.measurements_flat')) AS flat_total
FROM pg_partition_tree('lab_ops.measurements_archive')
WHERE isleaf;

-- === 4. Retención: borrar enero de 2025 ===
-- Qué observar: DETACH + DROP elimina una partición entera casi al instante y sin filas
-- muertas. El DELETE debe marcar cada fila (~223.000) y deja n_dead_tup alto hasta el VACUUM.
-- Los tiempos aparecen como avisos (NOTICE; pestaña Messages en pgAdmin).
-- Particionada: DETACH PARTITION + DROP TABLE. Común: DELETE de las mismas filas.
DO $timing$
DECLARE
    t0 timestamptz;
BEGIN
    t0 := clock_timestamp();
    ALTER TABLE lab_ops.measurements_archive DETACH PARTITION lab_ops.measurements_archive_2025_01;
    DROP TABLE lab_ops.measurements_archive_2025_01;
    RAISE NOTICE 'Particionada (DETACH + DROP): % ms', round(extract(epoch FROM clock_timestamp() - t0) * 1000, 1);

    t0 := clock_timestamp();
    DELETE FROM lab_ops.measurements_flat WHERE measured_at < '2025-02-01';
    RAISE NOTICE 'Común (DELETE): % ms', round(extract(epoch FROM clock_timestamp() - t0) * 1000, 1);
END
$timing$;
SELECT pg_stat_force_next_flush();
SELECT pg_sleep(1);
SELECT relname, n_live_tup, n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'lab_ops' AND relname = 'measurements_flat';
-- Esas filas muertas siguen ocupando espacio hasta que corra VACUUM:
SELECT pg_size_pretty(pg_total_relation_size('lab_ops.measurements_flat')) AS flat_antes_del_vacuum;
VACUUM lab_ops.measurements_flat;
SELECT pg_stat_force_next_flush();
SELECT pg_sleep(1);
SELECT n_live_tup, n_dead_tup FROM pg_stat_user_tables
WHERE schemaname = 'lab_ops' AND relname = 'measurements_flat';
-- VACUUM las marcó como reutilizables, pero el archivo no se achica (sólo VACUUM FULL lo haría):
SELECT pg_size_pretty(pg_total_relation_size('lab_ops.measurements_flat')) AS flat_despues_del_vacuum;

-- === 5. Variante LIST: una partición por organización ===
-- Qué observar: cada tenant queda en su propia tabla física; filtrar por organization_id
-- poda la otra partición. Es otra forma de aislar tenants (distinta de RLS).
CREATE TABLE lab_ops.measurements_by_org (
    organization_id bigint NOT NULL,
    device_id       text NOT NULL,
    measured_at     timestamptz NOT NULL,
    value           numeric(12, 3) NOT NULL
) PARTITION BY LIST (organization_id);
CREATE TABLE lab_ops.measurements_by_org_1 PARTITION OF lab_ops.measurements_by_org FOR VALUES IN (1);
CREATE TABLE lab_ops.measurements_by_org_2 PARTITION OF lab_ops.measurements_by_org FOR VALUES IN (2);
INSERT INTO lab_ops.measurements_by_org
SELECT 1 + g % 2, 'SIM-' || (g % 8 + 1), timestamptz '2025-06-01' + g * interval '1 minute', g % 10
FROM generate_series(1, 20000) AS g;
SELECT tableoid::regclass AS particion, organization_id, count(*) AS filas
FROM lab_ops.measurements_by_org
GROUP BY 1, 2
ORDER BY 1;
EXPLAIN (COSTS OFF)
SELECT count(*) FROM lab_ops.measurements_by_org WHERE organization_id = 2;

-- === 6. TimescaleDB: lo mismo, pero automático (chunks) ===
-- Qué observar: la hipertabla public.measurements ya está particionada por tiempo
-- en chunks, sin crear ni mantener particiones a mano.
SELECT show_chunks('public.measurements') AS chunk;
SELECT chunk_name, pg_size_pretty(total_bytes) AS tamano
FROM chunks_detailed_size('public.measurements')
ORDER BY chunk_name;
-- --> Exclusión de chunks: con un rango angosto el plan nombra sólo el chunk que lo contiene
--     (la hipertabla tiene 2 chunks; el otro no aparece).
EXPLAIN (COSTS OFF)
SELECT count(*) FROM public.measurements
WHERE measured_at >= now() - interval '1 day';
-- --> Retención: drop_chunks es el DETACH+DROP automático. NO se aplica a los datos reales;
--     se prueba sobre una hipertabla de práctica con datos de 2025.
CREATE TABLE lab_ops.ts_demo (
    measured_at timestamptz NOT NULL,
    value       numeric(12, 3) NOT NULL
);
SELECT create_hypertable('lab_ops.ts_demo', 'measured_at', chunk_time_interval => interval '1 month');
INSERT INTO lab_ops.ts_demo
SELECT timestamptz '2025-01-01' + g * interval '10 minutes', g % 50
FROM generate_series(0, 52000) AS g;
SELECT count(*) AS chunks_antes FROM show_chunks('lab_ops.ts_demo');
-- Tiempo de drop_chunks (aparece como aviso en la pestaña Messages):
DO $timing$
DECLARE
    t0 timestamptz := clock_timestamp();
BEGIN
    PERFORM drop_chunks('lab_ops.ts_demo', older_than => timestamptz '2025-07-01');
    RAISE NOTICE 'drop_chunks: % ms', round(extract(epoch FROM clock_timestamp() - t0) * 1000, 1);
END
$timing$;
SELECT count(*) AS chunks_despues FROM show_chunks('lab_ops.ts_demo');
-- En datos reales se automatiza con: SELECT add_retention_policy('public.measurements', interval '1 year');

-- === 7. Permisos: lab_ops no es de nadie más ===
-- Qué observar: ningún rol de aplicación ve el esquema (todas las respuestas en f).
SELECT r AS rol, has_schema_privilege(r, 'lab_ops', 'USAGE') AS puede_usar_lab_ops
FROM unnest(ARRAY['ai_readonly', 'rag_readonly', 'rag_ingest', 'app_iot']) AS r;

-- Fin. Explorá lab_ops en pgAdmin. Para limpiar:  DROP SCHEMA lab_ops CASCADE;
