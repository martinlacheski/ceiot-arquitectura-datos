-- CONTEXTO
-- Practicar DDL y DML sin modificar las 72 mediciones canónicas. La tabla auxiliar admite notas.

-- EJEMPLO EJECUTABLE 1 (DDL seguro): crear la tabla solo si no existe.
CREATE TABLE IF NOT EXISTS measurement_annotations (
    id UUID PRIMARY KEY,
    measurement_id UUID NOT NULL REFERENCES measurements(id) ON DELETE CASCADE,
    note TEXT NOT NULL CHECK (btrim(note) <> ''),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- OBSERVACIÓN ESPERADA
-- pgAdmin muestra measurement_annotations con PK, FK, NOT NULL y CHECK.

-- EJEMPLO EJECUTABLE 2 (INSERT simple y repetible): crear o restaurar una fila.
INSERT INTO measurement_annotations (id, measurement_id, note, reviewed_at, created_at)
VALUES (
    'd0000001-0000-4000-8000-000000000001',
    'b0000001-0000-4000-8000-000000000001',
    'Lectura revisada durante la práctica',
    NULL,
    '2024-02-01T12:00:00Z'
)
ON CONFLICT (id) DO UPDATE SET
    measurement_id = EXCLUDED.measurement_id,
    note = EXCLUDED.note,
    reviewed_at = EXCLUDED.reviewed_at,
    created_at = EXCLUDED.created_at;

SELECT id, measurement_id, note, reviewed_at, created_at
FROM measurement_annotations
WHERE id = 'd0000001-0000-4000-8000-000000000001';

-- OBSERVACIÓN ESPERADA
-- Un INSERT simple agrega una fila por cada grupo VALUES. ON CONFLICT vuelve repetible
-- el ejemplo y deja exactamente una nota canónica vinculada con una medición existente.

-- EJEMPLO EJECUTABLE 3 (INSERT de varias filas): una sentencia, dos filas descartables.
BEGIN;

INSERT INTO measurement_annotations (id, measurement_id, note, reviewed_at, created_at)
VALUES
    (
        'd0000003-0000-4000-8000-000000000003',
        'b0000003-0000-4000-8000-000000000003',
        'Primera fila del INSERT múltiple',
        NULL,
        '2024-02-01T12:10:00Z'
    ),
    (
        'd0000004-0000-4000-8000-000000000004',
        'b0000004-0000-4000-8000-000000000004',
        'Segunda fila del INSERT múltiple',
        NULL,
        '2024-02-01T12:11:00Z'
    );

SELECT id, measurement_id, note
FROM measurement_annotations
WHERE id IN (
    'd0000003-0000-4000-8000-000000000003',
    'd0000004-0000-4000-8000-000000000004'
)
ORDER BY id;

ROLLBACK;

-- OBSERVACIÓN ESPERADA
-- El SELECT dentro de la transacción muestra dos filas; ROLLBACK las descarta.

-- EJEMPLO EJECUTABLE 4 (UPDATE): primero seleccionar el objetivo exacto.
SELECT id, note, reviewed_at
FROM measurement_annotations
WHERE id = 'd0000001-0000-4000-8000-000000000001';

UPDATE measurement_annotations
SET note = 'Lectura revisada y comentada',
    reviewed_at = '2024-02-02T12:00:00Z'
WHERE id = 'd0000001-0000-4000-8000-000000000001'
RETURNING id, note, reviewed_at;

-- RECUPERACIÓN DEL UPDATE: restaurar inmediatamente la fila canónica.
UPDATE measurement_annotations
SET note = 'Lectura revisada durante la práctica',
    reviewed_at = NULL
WHERE id = 'd0000001-0000-4000-8000-000000000001'
RETURNING id, note, reviewed_at;

-- EJEMPLO EJECUTABLE 5 (DELETE): crear una fila descartable, verla y borrarla.
INSERT INTO measurement_annotations (id, measurement_id, note, reviewed_at, created_at)
VALUES (
    'd0000002-0000-4000-8000-000000000002',
    'b0000002-0000-4000-8000-000000000002',
    'Nota temporal para practicar DELETE',
    NULL,
    '2024-02-01T12:05:00Z'
)
ON CONFLICT (id) DO UPDATE SET note = EXCLUDED.note;

SELECT id, measurement_id, note
FROM measurement_annotations
WHERE id = 'd0000002-0000-4000-8000-000000000002';

DELETE FROM measurement_annotations
WHERE id = 'd0000002-0000-4000-8000-000000000002'
RETURNING id, measurement_id, note;

-- EJEMPLO EJECUTABLE 6: FK y CHECK rechazan datos inválidos sin detener el archivo.
DO $demo$
BEGIN
    BEGIN
        INSERT INTO measurement_annotations (id, measurement_id, note)
        VALUES (
            'd0000005-0000-4000-8000-000000000005',
            'b9999999-9999-4999-8999-999999999999',
            'Esta FK no existe'
        );
        RAISE EXCEPTION 'La FK inválida fue aceptada inesperadamente';
    EXCEPTION
        WHEN foreign_key_violation THEN
            RAISE NOTICE 'FK rechazada como se esperaba: %', SQLERRM;
    END;

    BEGIN
        INSERT INTO measurement_annotations (id, measurement_id, note)
        VALUES (
            'd0000006-0000-4000-8000-000000000006',
            'b0000006-0000-4000-8000-000000000006',
            '   '
        );
        RAISE EXCEPTION 'El CHECK inválido fue aceptado inesperadamente';
    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'CHECK rechazado como se esperaba: %', SQLERRM;
    END;
END
$demo$;

-- OBSERVACIÓN ESPERADA
-- PostgreSQL informa ambos rechazos como NOTICE. Los bloques EXCEPTION revierten solo
-- cada intento inválido y permiten continuar aun con psql -v ON_ERROR_STOP=1.

-- EJEMPLO EJECUTABLE 7: ON DELETE CASCADE borra automáticamente la nota dependiente.
BEGIN;

INSERT INTO measurements (id, device_id, variable, value, unit, recorded_at, created_at)
VALUES (
    'e0000001-0000-4000-8000-000000000001',
    '44444444-4444-4444-4444-444444444444',
    'temperature',
    23.5,
    'C',
    '2024-02-10T10:00:00Z',
    '2024-02-10T10:00:00Z'
);

INSERT INTO measurement_annotations (id, measurement_id, note, created_at)
VALUES (
    'f0000001-0000-4000-8000-000000000001',
    'e0000001-0000-4000-8000-000000000001',
    'Nota dependiente para observar CASCADE',
    '2024-02-10T10:01:00Z'
);

SELECT COUNT(*) AS disposable_annotation_before_delete
FROM measurement_annotations
WHERE id = 'f0000001-0000-4000-8000-000000000001';

DELETE FROM measurements
WHERE id = 'e0000001-0000-4000-8000-000000000001';

SELECT COUNT(*) AS disposable_annotation_after_delete
FROM measurement_annotations
WHERE id = 'f0000001-0000-4000-8000-000000000001';

ROLLBACK;

-- OBSERVACIÓN ESPERADA
-- Antes del DELETE el conteo es 1; después es 0 porque la FK auxiliar declara CASCADE.
-- ROLLBACK elimina toda la demostración descartable y conserva las 72 mediciones.

-- EJEMPLO EJECUTABLE 8: ON DELETE RESTRICT impide borrar un dispositivo referenciado.
DO $demo$
BEGIN
    BEGIN
        DELETE FROM devices
        WHERE id = '44444444-4444-4444-4444-444444444444';
        RAISE EXCEPTION 'RESTRICT no protegió el dispositivo referenciado';
    EXCEPTION
        WHEN foreign_key_violation THEN
            RAISE NOTICE 'RESTRICT impidió el DELETE como se esperaba: %', SQLERRM;
    END;
END
$demo$;

SELECT COUNT(*) AS protected_device_count
FROM devices
WHERE id = '44444444-4444-4444-4444-444444444444';

SELECT COUNT(*) AS canonical_measurement_count
FROM measurements;

-- OBSERVACIÓN ESPERADA
-- El dispositivo sigue presente (1) porque measurements lo referencia con RESTRICT.
-- El conteo canónico final de measurements continúa en 72.

-- VARIACIONES SEGURAS
-- Modificar únicamente note de la fila d0000001... y ejecutar luego su recuperación.
-- Crear notas descartables sobre mediciones existentes dentro de BEGIN/ROLLBACK.

-- RECUPERACIÓN TOTAL DE ESTA PRÁCTICA AUXILIAR (opcional y segura para measurements):
-- DELETE FROM measurement_annotations;
-- Luego volver a ejecutar este archivo para recrear la nota canónica.
