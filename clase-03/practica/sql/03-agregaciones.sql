-- CONTEXTO
-- Resumir muchas mediciones con agregaciones, GROUP BY y HAVING sin mezclar unidades.

-- EJEMPLO EJECUTABLE 1: agregaciones sobre las 72 mediciones canónicas.
SELECT
    COUNT(*) AS measurement_count,
    MIN(recorded_at) AS first_recorded_at,
    MAX(recorded_at) AS last_recorded_at
FROM measurements;

-- OBSERVACIÓN ESPERADA
-- measurement_count = 72. MIN y MAX delimitan el período del seed.

-- EJEMPLO EJECUTABLE 2: GROUP BY variable y unidad.
SELECT
    variable,
    unit,
    COUNT(*) AS sample_count,
    ROUND(AVG(value), 2) AS average_value,
    MIN(value) AS minimum_value,
    MAX(value) AS maximum_value
FROM measurements
GROUP BY variable, unit
ORDER BY variable ASC, unit ASC;

-- OBSERVACIÓN ESPERADA
-- Hay siete filas, una por combinación variable/unidad; no se comparan magnitudes distintas.

-- EJEMPLO EJECUTABLE 3: WHERE filtra filas antes de agrupar; HAVING filtra grupos después.
SELECT
    variable,
    unit,
    COUNT(*) AS sample_count_before_jan_15,
    ROUND(AVG(value), 2) AS average_value_before_jan_15
FROM measurements
WHERE recorded_at < TIMESTAMPTZ '2024-01-15 00:00:00+00'
GROUP BY variable, unit
HAVING COUNT(*) >= 5
ORDER BY variable ASC, unit ASC;

-- OBSERVACIÓN ESPERADA
-- WHERE primero limita las filas al período anterior al 15 de enero. Después GROUP BY
-- forma siete combinaciones variable/unidad y HAVING conserva cuatro: co2, humidity,
-- temperature y voltage. current, power y soil_moisture sí se agrupan, pero se eliminan
-- porque tienen menos de cinco muestras dentro de ese período.

-- VARIACIONES SEGURAS
-- Cambiar el límite temporal de WHERE para observar cómo cambia cada grupo.
-- Cambiar HAVING COUNT(*) >= 5 por >= 7: HAVING sigue evaluando el resumen, no cada fila.
-- Quitar solo HAVING para ver los siete grupos producidos después del WHERE.

-- RECUPERACIÓN
-- No hace falta: todos los ejemplos son SELECT.
