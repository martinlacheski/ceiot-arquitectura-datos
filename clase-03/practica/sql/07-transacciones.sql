-- CONTEXTO
-- Una transacción agrupa cambios. COMMIT los persiste; ROLLBACK los deshace.
-- Ejecute antes 06-ddl-dml-seguro.sql para disponer de measurement_annotations.

-- EJEMPLO EJECUTABLE 1: observar, modificar dentro de la transacción y deshacer.
SELECT id, note, reviewed_at
FROM measurement_annotations
WHERE id = 'd0000001-0000-4000-8000-000000000001';

BEGIN;

UPDATE measurement_annotations
SET note = 'Cambio temporal dentro de una transacción',
    reviewed_at = '2024-02-03T12:00:00Z'
WHERE id = 'd0000001-0000-4000-8000-000000000001'
RETURNING id, note, reviewed_at;

SELECT id, note, reviewed_at
FROM measurement_annotations
WHERE id = 'd0000001-0000-4000-8000-000000000001';

ROLLBACK;

-- VERIFICACIÓN DESPUÉS DEL ROLLBACK.
SELECT id, note, reviewed_at
FROM measurement_annotations
WHERE id = 'd0000001-0000-4000-8000-000000000001';

-- OBSERVACIÓN ESPERADA
-- Dentro de BEGIN se ve el texto temporal. Después de ROLLBACK vuelve el texto
-- 'Lectura revisada durante la práctica' y reviewed_at vuelve a NULL.

-- EJEMPLO EJECUTABLE 2: COMMIT persiste una fila descartable.
-- Esta limpieza puntual permite repetir el archivo si una ejecución anterior se interrumpió.
DELETE FROM measurement_annotations
WHERE id = 'd0000007-0000-4000-8000-000000000007';

BEGIN;

INSERT INTO measurement_annotations (id, measurement_id, note, reviewed_at, created_at)
VALUES (
    'd0000007-0000-4000-8000-000000000007',
    'b0000007-0000-4000-8000-000000000007',
    'Fila descartable confirmada con COMMIT',
    NULL,
    '2024-02-03T12:10:00Z'
);

COMMIT;

-- VERIFICACIÓN EN UNA SENTENCIA POSTERIOR: la fila sobrevivió al COMMIT.
SELECT id, measurement_id, note
FROM measurement_annotations
WHERE id = 'd0000007-0000-4000-8000-000000000007';

-- RECUPERACIÓN DEL EJEMPLO CONFIRMADO: borrar únicamente la fila descartable.
DELETE FROM measurement_annotations
WHERE id = 'd0000007-0000-4000-8000-000000000007'
RETURNING id, measurement_id, note;

SELECT COUNT(*) AS committed_disposable_row_after_cleanup
FROM measurement_annotations
WHERE id = 'd0000007-0000-4000-8000-000000000007';

SELECT COUNT(*) AS canonical_measurement_count
FROM measurements;

-- OBSERVACIÓN ESPERADA
-- El SELECT posterior a COMMIT muestra una fila persistida. La limpieza devuelve esa fila,
-- el conteo descartable final es 0 y measurements permanece en 72.

-- VARIACIONES SEGURAS
-- Cambiar el texto temporal del primer bloque y conservar ROLLBACK.
-- Repetir el bloque COMMIT completo: la limpieza inicial evita conflicto con su UUID.

-- RECUPERACIÓN
-- ROLLBACK recupera el primer ejemplo; el DELETE exacto recupera el segundo.
-- Si se interrumpe después de COMMIT, vuelva a ejecutar este archivo o borre solo d0000007...
