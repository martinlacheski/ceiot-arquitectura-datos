-- CONTEXTO
-- Errores frecuentes y alternativas seguras. Los errores de sintaxis o restricciones se
-- capturan en bloques EXCEPTION o quedan comentados: el archivo completo puede ejecutarse
-- con psql -v ON_ERROR_STOP=1 y no deja cambios dañinos.

-- EJEMPLO 1: = NULL no es verdadero; toda comparación con NULL produce UNKNOWN.
SELECT COUNT(*) AS incorrect_equal_null_count
FROM device_status_history
WHERE ended_at = NULL;

-- ALTERNATIVA CORRECTA.
SELECT COUNT(*) AS current_status_count
FROM device_status_history
WHERE ended_at IS NULL;

-- OBSERVACIÓN ESPERADA
-- La primera consulta devuelve 0, no 6. La segunda devuelve los seis estados actuales.

-- EJEMPLO 2: un UPDATE sin WHERE tiene alcance global. Se observa y se deshace.
BEGIN;

SELECT COUNT(*) AS rows_that_unsafe_update_would_touch
FROM measurement_annotations;

UPDATE measurement_annotations
SET note = 'Cambio global inseguro para observar dentro de ROLLBACK'
RETURNING id, note;

ROLLBACK;

-- ALTERNATIVA CORRECTA: previsualizar y limitar por una clave única.
BEGIN;

SELECT id, note
FROM measurement_annotations
WHERE id = 'd0000001-0000-4000-8000-000000000001';

UPDATE measurement_annotations
SET note = 'Cambio puntual y controlado'
WHERE id = 'd0000001-0000-4000-8000-000000000001'
RETURNING id, note;

ROLLBACK;

-- EJEMPLO 3: un DELETE sin WHERE borra todo su objetivo. Se observa y se deshace.
BEGIN;

DELETE FROM measurement_annotations
RETURNING id, note;

ROLLBACK;

-- ALTERNATIVA CORRECTA (comentada para preservar la nota canónica): seleccionar primero
-- y usar la misma clave única en DELETE.
SELECT id, note
FROM measurement_annotations
WHERE id = 'd0000001-0000-4000-8000-000000000001';
-- DELETE FROM measurement_annotations
-- WHERE id = 'd0000001-0000-4000-8000-000000000001';

-- OBSERVACIÓN ESPERADA
-- Los dos bloques peligrosos solo afectan temporalmente la tabla auxiliar. ROLLBACK
-- restaura todo. La alternativa hace visible y limita el objetivo a una sola fila.

-- EJEMPLO 4: una FK inexistente y un CHECK falso son rechazados de forma controlada.
DO $demo$
BEGIN
    BEGIN
        INSERT INTO measurement_annotations (id, measurement_id, note)
        VALUES (
            'f0000002-0000-4000-8000-000000000002',
            'b9999999-9999-4999-8999-999999999999',
            'Medición inexistente'
        );
    EXCEPTION
        WHEN foreign_key_violation THEN
            RAISE NOTICE 'Error FK capturado: use un measurement_id existente. Detalle: %', SQLERRM;
    END;

    BEGIN
        INSERT INTO measurement_annotations (id, measurement_id, note)
        VALUES (
            'f0000003-0000-4000-8000-000000000003',
            'b0000003-0000-4000-8000-000000000003',
            ''
        );
    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'Error CHECK capturado: note no puede estar vacío. Detalle: %', SQLERRM;
    END;
END
$demo$;

-- ALTERNATIVA CORRECTA: valores que satisfacen FK y CHECK dentro de una transacción descartable.
BEGIN;

INSERT INTO measurement_annotations (id, measurement_id, note)
VALUES (
    'f0000004-0000-4000-8000-000000000004',
    'b0000004-0000-4000-8000-000000000004',
    'FK existente y texto no vacío'
)
RETURNING id, measurement_id, note;

ROLLBACK;

-- EJEMPLO 5: seleccionar una columna no agregada fuera de GROUP BY es inválido.
DO $demo$
BEGIN
    BEGIN
        EXECUTE 'SELECT device_id, variable, COUNT(*) FROM measurements GROUP BY device_id';
    EXCEPTION
        WHEN grouping_error THEN
            RAISE NOTICE 'GROUP BY inválido capturado: variable no estaba agrupada. Detalle: %', SQLERRM;
    END;
END
$demo$;

-- ALTERNATIVA CORRECTA: agrupar todas las dimensiones seleccionadas.
SELECT device_id, variable, unit, COUNT(*) AS sample_count
FROM measurements
GROUP BY device_id, variable, unit
ORDER BY device_id, variable, unit;

-- EJEMPLO 6: id es ambiguo cuando ambas tablas del join lo tienen.
DO $demo$
BEGIN
    BEGIN
        EXECUTE 'SELECT id FROM devices AS d INNER JOIN measurements AS m ON m.device_id = d.id';
    EXCEPTION
        WHEN ambiguous_column THEN
            RAISE NOTICE 'Columna ambigua capturada: califique id con su alias. Detalle: %', SQLERRM;
    END;
END
$demo$;

-- ALTERNATIVA CORRECTA: cada columna compartida lleva alias explícito.
SELECT d.id AS device_id, m.id AS measurement_id
FROM devices AS d
INNER JOIN measurements AS m ON m.device_id = d.id
ORDER BY d.id, m.id
LIMIT 5;

-- EJEMPLO 7: recuperación de un error dentro de una unidad transaccional.
-- Sin manejo, la secuencia siguiente deja la transacción abortada hasta ROLLBACK:
-- BEGIN;
-- SELECT 1 / 0;
-- SELECT 'PostgreSQL respondería: current transaction is aborted';
-- ROLLBACK;
-- La alternativa runnable usa EXCEPTION: PostgreSQL crea una subtransacción, revierte
-- la sentencia fallida y permite que la transacción exterior continúe.
BEGIN;

DO $demo$
BEGIN
    BEGIN
        PERFORM 1 / 0;
    EXCEPTION
        WHEN division_by_zero THEN
            RAISE NOTICE 'Error capturado; la subtransacción fallida fue revertida';
    END;
END
$demo$;

SELECT 'La transacción exterior continúa utilizable' AS recovery_result;
COMMIT;

-- EJEMPLO 8: concatenación de aplicación versus parámetros del driver.
-- Incorrecto (comentado; no construir SQL con entrada concatenada):
-- query = "SELECT * FROM measurements WHERE variable = '" + user_input + "'"
-- cursor.execute(query)
--
-- Correcto, como en client/query.py: SQL estático y valores enviados por separado.
-- query = "SELECT * FROM measurements WHERE variable = %s"
-- cursor.execute(query, (user_input,))
-- Los marcadores %s pertenecen al driver Python, no son sintaxis para pegar y ejecutar
-- directamente en Query Tool.

-- VERIFICACIÓN FINAL: ningún ejemplo alteró el punto de partida canónico.
SELECT COUNT(*) AS canonical_measurement_count
FROM measurements;

SELECT id, note, reviewed_at
FROM measurement_annotations
WHERE id = 'd0000001-0000-4000-8000-000000000001';

-- OBSERVACIÓN ESPERADA
-- measurements = 72 y la nota canónica conserva 'Lectura revisada durante la práctica'.

-- RECUPERACIÓN
-- Los ejemplos mutables ya terminaron en ROLLBACK. Si se copia por separado una sentencia
-- incorrecta y la sesión queda en estado abortado, ejecutar ROLLBACK; antes de continuar.
