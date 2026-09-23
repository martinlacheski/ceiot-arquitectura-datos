-- CONTEXTO: elimina únicamente la fila agregada por la variación segura.
-- EJEMPLO EJECUTABLE: usa la clave primaria completa para recuperar la partición.
-- OBSERVACIÓN ESPERADA: la consulta explícita de las 10:30:00 devuelve cero filas.
-- VARIACIONES SEGURAS: repetir DELETE conserva el mismo resultado.
-- RECUPERACIÓN: la propia eliminación es idempotente y su SELECT confirma el estado.

DELETE FROM measurement_by_device_day
WHERE device_id = 'AIR-002'
  AND day = '2025-05-12'
  AND measured_at = '2025-05-12T10:30:00Z'
  AND variable = 'co2';

SELECT measured_at, variable, value
FROM measurement_by_device_day
WHERE device_id = 'AIR-002'
  AND day = '2025-05-12'
  AND measured_at = '2025-05-12T10:30:00Z';
