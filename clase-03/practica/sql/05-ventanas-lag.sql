-- CONTEXTO
-- Una función de ventana compara filas sin colapsarlas como GROUP BY.

-- EJEMPLO EJECUTABLE: LAG por dispositivo y variable.
WITH measurement_changes AS (
    SELECT
        m.id,
        d.serial_number,
        m.device_id,
        m.variable,
        m.value,
        m.unit,
        m.recorded_at,
        LAG(m.value) OVER (
            PARTITION BY m.device_id, m.variable
            ORDER BY m.recorded_at ASC, m.id ASC
        ) AS previous_value
    FROM measurements AS m
    INNER JOIN devices AS d ON d.id = m.device_id
)
SELECT
    serial_number,
    variable,
    value,
    previous_value,
    value - previous_value AS change_from_previous,
    unit,
    recorded_at
FROM measurement_changes
ORDER BY serial_number ASC, variable ASC, recorded_at ASC, id ASC;

-- OBSERVACIÓN ESPERADA
-- La primera fila de cada par dispositivo/variable tiene previous_value NULL.
-- Las siguientes muestran el cambio respecto de la muestra anterior del mismo par.

-- VARIACIONES SEGURAS
-- Agregar WHERE variable = 'temperature' en el SELECT exterior.
-- Cambiar el SELECT exterior para mostrar ABS(value - previous_value).
-- No quitar device_id ni variable de PARTITION BY: evitaría mezclar series diferentes.

-- RECUPERACIÓN
-- No hace falta: el ejemplo solamente lee datos.
