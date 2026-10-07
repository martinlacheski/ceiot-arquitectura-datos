-- Series de tiempo con TimescaleDB (hypertable, time_bucket y consultas por ventana).
--
--   docker compose --env-file .env -f compose.yaml exec postgres sh -c \
--     'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /lab/examples/01-temporal.sql'
--
-- Desde pgAdmin: abrí el archivo (Open File → Shared Storage → examples), seleccioná un
-- bloque y ejecutalo con F5; ejecutar todo el archivo muestra sólo el último resultado,
-- los avisos (NOTICE) aparecen en la pestaña Messages.

-- La tabla debe ser una hypertable particionada por measured_at.
SELECT hypertable_name, num_dimensions
FROM timescaledb_information.hypertables
WHERE hypertable_schema = 'public'
  AND hypertable_name = 'measurements';

-- Resultado esperado: 2 filas para CO2 de AIR-002.
-- 10:31Z -> 2 muestras, promedio 802.5 ppm.
-- 10:32Z -> 1 muestra, promedio 812.0 ppm.
SELECT
    time_bucket('1 minute', measured_at) AS minute,
    count(*) AS sample_count,
    round(avg(value), 1) AS average_value,
    min(unit) AS unit
FROM measurements
WHERE device_id = 'AIR-002'
  AND variable = 'co2'
  AND measured_at >= '2025-05-12T10:31:00Z'
  AND measured_at < '2025-05-12T10:33:00Z'
GROUP BY minute
ORDER BY minute;

-- Resultado esperado sobre el día histórico fijo 2025-05-12: 8 filas
-- totales y 5 para AIR-002. El total global de measurements crece con el
-- historial horario reciente de ENV-X, por eso este conteo se acota a esa
-- fecha para seguir siendo un observable estable.
SELECT
    count(*) AS total_measurements_2025_05_12,
    count(*) FILTER (WHERE device_id = 'AIR-002') AS air_002_measurements
FROM measurements
WHERE measured_at >= '2025-05-12T00:00:00Z'
  AND measured_at < '2025-05-13T00:00:00Z';

-- "¿Cuál fue la temperatura promedio del Aula 204 durante las últimas 24
-- horas?" (filmina Clase 6). Recorre locations -> devices -> measurements,
-- como piden las notas del orador. Siempre hay datos: el seed ancla 48 horas
-- de temperatura de ENV-X (AMB-001) a la hora de ejecución.
SELECT
    round(avg(measurement.value), 1) AS average_temperature_c,
    count(*) AS sample_count
FROM measurements AS measurement
JOIN devices AS device ON device.device_id = measurement.device_id
JOIN locations AS location ON location.location_id = device.location_id
WHERE location.name = 'Aula 204'
  AND measurement.variable = 'temperature'
  AND measurement.measured_at >= now() - interval '24 hours';

-- Misma pregunta desglosada por hora, para observar el patrón determinista
-- (incluidas las horas SUSPECT recientes) en vez de un único promedio.
SELECT
    time_bucket('1 hour', measurement.measured_at) AS hour,
    round(avg(measurement.value), 1) AS average_temperature_c,
    count(*) AS sample_count,
    bool_or(measurement.quality = 'SUSPECT') AS has_suspect_reading
FROM measurements AS measurement
JOIN devices AS device ON device.device_id = measurement.device_id
JOIN locations AS location ON location.location_id = device.location_id
WHERE location.name = 'Aula 204'
  AND measurement.variable = 'temperature'
  AND measurement.measured_at >= now() - interval '24 hours'
GROUP BY hour
ORDER BY hour;
