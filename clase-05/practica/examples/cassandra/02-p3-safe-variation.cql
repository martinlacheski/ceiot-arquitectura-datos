-- CONTEXTO: una identidad estable vuelve idempotente el reintento de escritura.
-- EJEMPLO EJECUTABLE: inserta dos veces la misma medición de prueba con la clave primaria completa.
-- OBSERVACIÓN ESPERADA: la clave primaria identifica una sola fila a las 10:30:00.
-- VARIACIONES SEGURAS: cambiar value conservando la misma identidad.
-- RECUPERACIÓN: ejecutar 03-p3-recover.cql para eliminar solo la fila de prueba.

INSERT INTO measurement_by_device_day
(device_id, day, measured_at, variable, value, unit, quality)
VALUES ('AIR-002', '2025-05-12', '2025-05-12T10:30:00Z', 'co2', 790, 'ppm', 'GOOD');

INSERT INTO measurement_by_device_day
(device_id, day, measured_at, variable, value, unit, quality)
VALUES ('AIR-002', '2025-05-12', '2025-05-12T10:30:00Z', 'co2', 790, 'ppm', 'GOOD');

SELECT measured_at, variable, value
FROM measurement_by_device_day
WHERE device_id = 'AIR-002'
  AND day = '2025-05-12'
  AND measured_at = '2025-05-12T10:30:00Z';
