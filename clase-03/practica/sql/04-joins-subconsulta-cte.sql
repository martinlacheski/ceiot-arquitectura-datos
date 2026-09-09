-- CONTEXTO
-- Conectar relaciones y construir consultas por etapas con joins, subconsultas y CTE.

-- EJEMPLO EJECUTABLE 1: INNER JOIN conserva filas con coincidencia.
SELECT
    d.serial_number,
    m.variable,
    m.value,
    m.unit,
    m.recorded_at
FROM measurements AS m
INNER JOIN devices AS d ON d.id = m.device_id
WHERE m.variable = 'temperature'
ORDER BY d.serial_number ASC, m.recorded_at ASC, m.id ASC;

-- OBSERVACIÓN ESPERADA
-- Cada medición muestra el serial de su dispositivo; no hay mediciones huérfanas por la FK.

-- EJEMPLO EJECUTABLE 2: LEFT JOIN conserva todas las filas de la tabla izquierda.
SELECT
    l.name AS location_name,
    d.serial_number,
    dlh.started_at
FROM locations AS l
LEFT JOIN device_location_history AS dlh
  ON dlh.location_id = l.id
 AND dlh.ended_at IS NULL
LEFT JOIN devices AS d ON d.id = dlh.device_id
ORDER BY l.name ASC, d.serial_number ASC NULLS LAST;

-- OBSERVACIÓN ESPERADA
-- Aparecen las cinco ubicaciones. Future Station C no tiene asignación actual y por eso
-- serial_number y started_at son NULL; las demás pueden aparecer más de una vez.

-- EJEMPLO EJECUTABLE 3: RIGHT JOIN conserva todas las filas de la tabla derecha.
SELECT
    l.name AS location_name,
    dlh.device_id,
    dlh.started_at
FROM device_location_history AS dlh
RIGHT JOIN locations AS l
  ON l.id = dlh.location_id
 AND dlh.ended_at IS NULL
ORDER BY l.name ASC, dlh.device_id ASC NULLS LAST;

-- OBSERVACIÓN ESPERADA
-- Produce la misma preservación de ubicaciones desde el lado derecho: Future Station C
-- aparece con device_id y started_at NULL.

-- EJEMPLO EJECUTABLE 4: FULL OUTER JOIN conserva ambos lados.
SELECT
    l.name AS location_name,
    d.serial_number,
    dlh.started_at
FROM locations AS l
FULL OUTER JOIN device_location_history AS dlh
  ON dlh.location_id = l.id
 AND dlh.ended_at IS NULL
LEFT JOIN devices AS d ON d.id = dlh.device_id
ORDER BY l.name ASC NULLS LAST, d.serial_number ASC NULLS LAST;

-- OBSERVACIÓN ESPERADA
-- Conserva ubicaciones y asignaciones actuales aunque faltara coincidencia de cualquiera
-- de los lados. En este seed se ve la ubicación sin asignación; no hay asignaciones huérfanas
-- porque las FK exigen una ubicación y un dispositivo existentes.

-- EJEMPLO EJECUTABLE 5: joins más agregación, separando variable y unidad.
SELECT
    o.name AS organization_name,
    d.serial_number,
    m.variable,
    m.unit,
    COUNT(m.id) AS measurement_count,
    ROUND(AVG(m.value), 2) AS average_value
FROM organizations AS o
INNER JOIN devices AS d ON d.organization_id = o.id
LEFT JOIN measurements AS m ON m.device_id = d.id
GROUP BY o.id, o.name, d.id, d.serial_number, m.variable, m.unit
ORDER BY o.name ASC, d.serial_number ASC, m.variable ASC NULLS LAST, m.unit ASC NULLS LAST;

-- OBSERVACIÓN ESPERADA
-- Cada fila resume una sola combinación dispositivo/variable/unidad. Cada combinación
-- canónica tiene cuatro mediciones y AVG nunca mezcla grados, porcentajes, ppm, V, A o W.

-- EJEMPLO EJECUTABLE 6: subconsulta escalar comparada con el promedio de temperature.
SELECT id, device_id, value, unit, recorded_at
FROM measurements
WHERE variable = 'temperature'
  AND value > (
      SELECT AVG(value)
      FROM measurements
      WHERE variable = 'temperature'
  )
ORDER BY value DESC, id ASC;

-- OBSERVACIÓN ESPERADA
-- Aparecen temperaturas superiores al promedio global de temperature.

-- EJEMPLO EJECUTABLE 7: CTE para nombrar etapas de una consulta.
WITH temperature_by_device AS (
    SELECT
        device_id,
        unit,
        COUNT(*) AS sample_count,
        ROUND(AVG(value), 2) AS average_temperature
    FROM measurements
    WHERE variable = 'temperature'
    GROUP BY device_id, unit
)
SELECT
    d.serial_number,
    t.unit,
    t.sample_count,
    t.average_temperature
FROM temperature_by_device AS t
INNER JOIN devices AS d ON d.id = t.device_id
ORDER BY t.average_temperature DESC, d.serial_number ASC;

-- OBSERVACIÓN ESPERADA
-- El CTE produce el resumen; la consulta exterior agrega nombres legibles y orden estable.

-- VARIACIONES SEGURAS
-- En el INNER JOIN cambiar temperature por humidity.
-- En los joins externos agregar un filtro por organization_id dentro de una subconsulta.
-- En el CTE reemplazar AVG por MAX y conservar GROUP BY.

-- RECUPERACIÓN
-- No hace falta: todos los ejemplos son SELECT.
