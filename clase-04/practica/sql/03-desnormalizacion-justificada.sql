-- CONTEXTO
-- Ejecutar después de sql/02-normalizacion.sql. La normalización es la regla
-- general, pero a veces se acepta una redundancia deliberada y documentada
-- cuando el costo de recalcular algo muy consultado supera el riesgo de
-- mantenerlo desincronizado. Aquí se agrega dispositivos.medicion_count como
-- EXCEPCIÓN justificada, no como práctica por defecto.

-- Columna redundante: cuenta de mediciones por dispositivo, mantenida a mano.
ALTER TABLE dispositivos ADD COLUMN IF NOT EXISTS medicion_count INTEGER NOT NULL DEFAULT 0;

UPDATE dispositivos AS d
SET medicion_count = (
    SELECT COUNT(*) FROM mediciones AS m WHERE m.dispositivo_id = d.id
);

-- EJEMPLO EJECUTABLE 1: la forma "siempre correcta", sin redundancia.
SELECT dispositivo_id, COUNT(*) AS mediciones
FROM mediciones
GROUP BY dispositivo_id
ORDER BY dispositivo_id ASC;

-- OBSERVACIÓN ESPERADA
-- 15 -> 10, 16 -> 8, 17 -> 12, 18 -> 10, 19 -> 10. Siempre exacto porque
-- agrega en el momento de la consulta, pero recorre toda la tabla mediciones.

-- EJEMPLO EJECUTABLE 2: la forma desnormalizada, con lectura directa de la columna.
SELECT id, nombre, medicion_count
FROM dispositivos
ORDER BY id ASC;

-- OBSERVACIÓN ESPERADA
-- Mismos números que el GROUP BY anterior, pero leídos en O(1) por fila de
-- dispositivos, sin tocar mediciones. Útil si esta cuenta se muestra en un
-- dashboard de alta frecuencia y dispositivos es una tabla pequeña.

-- EJEMPLO EJECUTABLE 3: demostrar el riesgo real de la redundancia.
-- Se inserta una medición nueva SIN actualizar medicion_count a propósito,
-- para hacer visible que el contador puede desincronizarse si algún camino
-- de escritura se olvida de mantenerlo.
INSERT INTO mediciones (dispositivo_id, "timestamp", variable, valor)
VALUES (15, '2026-03-06 10:30:00', 'temperatura', '23.8')
ON CONFLICT (dispositivo_id, "timestamp", variable) DO NOTHING;

SELECT
    d.id,
    d.nombre,
    d.medicion_count AS contador_desnormalizado,
    (SELECT COUNT(*) FROM mediciones AS m WHERE m.dispositivo_id = d.id) AS conteo_real
FROM dispositivos AS d
WHERE d.id = 15;

-- OBSERVACIÓN ESPERADA
-- contador_desnormalizado = 10 pero conteo_real = 11: la redundancia quedó
-- desincronizada porque el INSERT no actualizó medicion_count. Este es
-- exactamente el riesgo que justifica documentar la excepción y decidir
-- cómo se mantiene sincronizada (trigger, transacción aplicativa, job
-- periódico); aquí se hizo a mano para que el desfasaje sea observable.

-- RECUPERACIÓN: eliminar la medición de demostración y dejar el punto de
-- partida (50 mediciones, medicion_count sincronizado) exactamente como estaba.
DELETE FROM mediciones
WHERE dispositivo_id = 15
  AND "timestamp" = '2026-03-06 10:30:00'
  AND variable = 'temperatura';

UPDATE dispositivos AS d
SET medicion_count = (
    SELECT COUNT(*) FROM mediciones AS m WHERE m.dispositivo_id = d.id
);

SELECT COUNT(*) AS mediciones_totales FROM mediciones;
-- OBSERVACIÓN ESPERADA: 50 (de nuevo).

-- VARIACIONES SEGURAS
-- Repetir el ejemplo 3 con dispositivo_id = 18 en vez de 15.
-- Comparar el plan de EJEMPLO EJECUTABLE 1 (GROUP BY) contra un SELECT directo
-- de medicion_count con EXPLAIN ANALYZE para ver la diferencia de costo.
