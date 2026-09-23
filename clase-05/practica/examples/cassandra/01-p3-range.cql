-- CONTEXTO: P3 consulta una partición diaria acotada por dispositivo y tiempo.
-- EJEMPLO EJECUTABLE: recupera las cinco filas de AIR-002 en orden descendente.
-- OBSERVACIÓN ESPERADA: devuelve cinco filas; 10:32:00 aparece antes que 10:31:00.
-- VARIACIONES SEGURAS: reducir el rango sin omitir device_id ni day.
-- RECUPERACIÓN: esta lectura no modifica datos; puede repetirse sin cambios.

SELECT measured_at, variable, value, unit
FROM measurement_by_device_day
WHERE device_id = 'AIR-002'
  AND day = '2025-05-12'
  AND measured_at >= '2025-05-12T10:31:00Z'
  AND measured_at <= '2025-05-12T10:32:00Z';
