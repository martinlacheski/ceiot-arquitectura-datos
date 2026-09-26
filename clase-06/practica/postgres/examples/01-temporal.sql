\set ON_ERROR_STOP on

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

-- Resultado esperado: 8 filas totales y 5 para AIR-002.
SELECT
    count(*) AS total_measurements,
    count(*) FILTER (WHERE device_id = 'AIR-002') AS air_002_measurements
FROM measurements;
