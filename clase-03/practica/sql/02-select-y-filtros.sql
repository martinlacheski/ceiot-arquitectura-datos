-- CONTEXTO
-- Consultas de filas: proyección, alias, filtros booleanos, pertenencia, NULL, tiempo y orden estable.

-- EJEMPLO EJECUTABLE 1: SELECT, proyección y alias.
SELECT
    serial_number AS device_serial,
    name AS device_name,
    model AS device_model
FROM devices
ORDER BY device_serial ASC;

-- OBSERVACIÓN ESPERADA
-- Se proyectan tres atributos de los seis dispositivos y los encabezados usan alias.

-- EJEMPLO EJECUTABLE 2: WHERE con AND/OR y paréntesis explícitos.
SELECT id, device_id, variable, value, unit, recorded_at
FROM measurements
WHERE (variable = 'temperature' AND value >= 22)
   OR (variable = 'co2' AND value > 600)
ORDER BY recorded_at ASC, id ASC;

-- OBSERVACIÓN ESPERADA
-- Solo aparecen temperaturas >= 22 o mediciones de CO2 > 600. Los paréntesis
-- hacen visible la precedencia; id desempata y vuelve estable el orden.

-- EJEMPLO EJECUTABLE 3: IN expresa pertenencia a una lista.
SELECT serial_number, name, model
FROM devices
WHERE model IN ('Enviro-1', 'Enviro-2')
ORDER BY serial_number ASC;

-- OBSERVACIÓN ESPERADA
-- Aparecen los cuatro dispositivos ambientales; IN evita repetir varios OR.

-- EJEMPLO EJECUTABLE 4: NULL se consulta con IS NULL o IS NOT NULL.
SELECT device_id, status, started_at, ended_at
FROM device_status_history
WHERE ended_at IS NULL
ORDER BY started_at ASC, device_id ASC;

SELECT device_id, status, started_at, ended_at
FROM device_status_history
WHERE ended_at IS NOT NULL
ORDER BY ended_at ASC, device_id ASC;

-- OBSERVACIÓN ESPERADA
-- La primera consulta devuelve seis estados actuales. La segunda hace observable
-- el único estado cerrado: maintenance de CEIOT-A-01, terminado al comenzar su estado active.

-- EJEMPLO EJECUTABLE 5: BETWEEN incluye ambos extremos.
SELECT id, device_id, variable, value, unit, recorded_at
FROM measurements
WHERE variable = 'temperature'
  AND value BETWEEN 22.0 AND 23.0
ORDER BY value ASC, recorded_at ASC, id ASC;

-- OBSERVACIÓN ESPERADA
-- BETWEEN 22.0 AND 23.0 equivale a value >= 22.0 AND value <= 23.0:
-- tanto 22.0 como 23.0, si existieran, quedarían incluidos.

-- EJEMPLO EJECUTABLE 6: rango temporal semiabierto [inicio, fin).
SELECT id, device_id, variable, value, unit, recorded_at
FROM measurements
WHERE recorded_at >= TIMESTAMPTZ '2024-01-07 00:00:00+00'
  AND recorded_at <  TIMESTAMPTZ '2024-01-14 00:00:00+00'
ORDER BY recorded_at ASC, id ASC;

-- OBSERVACIÓN ESPERADA
-- Incluye el inicio y excluye el fin. Aunque BETWEEN es inclusivo y válido,
-- para períodos consecutivos se recomienda [inicio, fin): evita contar dos veces
-- una fila ubicada exactamente en el límite compartido.

-- VARIACIONES SEGURAS
-- Cambiar la lista de IN por ('Power-1') o agregar otro modelo existente.
-- Cambiar 'temperature' por 'humidity', o las fechas por otra semana de enero.
-- Mantener una última columna única (id) en ORDER BY para conservar estabilidad.

-- RECUPERACIÓN
-- No hace falta: todos los ejemplos son SELECT.
