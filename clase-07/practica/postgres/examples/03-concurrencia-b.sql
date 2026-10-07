-- Concurrencia (slides 40-47): PESTAÑA B de tres.
--
-- Abrí este archivo en la segunda pestaña de Query Tool (Open File → carpeta
-- examples → 03-concurrencia-b.sql), sobre la misma base que la pestaña A. Ver
-- 03-concurrencia-a.sql para la explicación completa del laboratorio.
--
-- Desde pgAdmin: seleccioná UN bloque "-- PASO n" y ejecutalo con F5; ejecutar todo el
-- archivo no sirve, porque los pasos de A y B se intercalan. Los pasos tienen la misma
-- numeración global (1 a 24). Esta pestaña ejecuta los pares: 2, 4, 7, 10, 13, 15, 16, 19,
-- 21 y 23 (más el PASO 0 de preparación). Ejecutá cada paso sólo cuando la pestaña A haya
-- terminado el anterior. Los avisos (NOTICE) y los errores aparecen en la pestaña Messages.
-- Cada paso usa BEGIN/COMMIT explícitos: la transacción queda abierta en la pestaña
-- entre un paso y el siguiente.

-- PASO 0 (B): preparación de la pestaña B. Ejecutalo una vez, antes del PASO 2.
SET ROLE app_iot;
SELECT set_config('app.tenant_id', '1', false);

-- === ESCENARIO a: actualización perdida (B es la que pisa) ===

-- PASO 2 (B): después de que A leyó en el PASO 1. Resultado esperado: 60.
-- B también lee 60 (A todavía no confirmó nada de lo que viene).
BEGIN;
SELECT sampling_interval_seconds AS leido FROM devices WHERE device_id = 'AMB-001';

-- PASO 4 (B): después de que A confirmó en el PASO 3. Escribí el valor que leíste en el
-- PASO 2 más 60 (60 + 60 = 120) y confirmá.
UPDATE devices SET sampling_interval_seconds = 120 WHERE device_id = 'AMB-001';
COMMIT;
-- B confirmó 120 usando su lectura vieja (60): sobreescribió el 30 de A sin error.

-- === ESCENARIO b: SELECT ... FOR UPDATE (B espera a A) ===

-- PASO 7 (B): después de que A tomó el bloqueo en el PASO 6. Pide el mismo bloqueo.
-- Esta pestaña queda ejecutando: está esperando el candado de A. Andá a la pestaña C
-- (PASO 8) y después a la A (PASO 9).
-- Cuando A confirme, B se destraba y devuelve 30 (el valor que dejó A, no el 60 original).
BEGIN;
SELECT sampling_interval_seconds AS leido FROM devices WHERE device_id = 'AMB-001' FOR UPDATE;

-- PASO 10 (B): escribí el valor que leíste en el PASO 7 más 10 (30 + 10 = 40) y confirmá.
UPDATE devices SET sampling_interval_seconds = 40 WHERE device_id = 'AMB-001';
COMMIT;
-- B confirmó 40. Ahora A muestra el resultado en el PASO 11.

-- === ESCENARIO c: REPEATABLE READ (B recibe un error de serialización) ===

-- PASO 13 (B): después de que A leyó en el PASO 12. Resultado esperado: 60.
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT sampling_interval_seconds AS leido FROM devices WHERE device_id = 'AMB-001';

-- PASO 15 (B): después de que A confirmó en el PASO 14. Escribí el valor que leíste en el
-- PASO 13 más 60 (60 + 60 = 120). El error es lo que queremos ver.
-- Observá: ERROR "could not serialize access due to concurrent update".
-- En vez de pisar el 30 de A, PostgreSQL rechaza la escritura. La transacción quedó abortada.
UPDATE devices SET sampling_interval_seconds = 120 WHERE device_id = 'AMB-001';

-- PASO 16 (B): REINTENTA la transacción completa (empieza con ROLLBACK, que cierra la
-- transacción abortada). La lectura ahora devuelve 30; escribí ese valor más 60
-- (30 + 60 = 90) y confirmá. Ahora A muestra el resultado en el PASO 17.
ROLLBACK;
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT sampling_interval_seconds AS leido FROM devices WHERE device_id = 'AMB-001';
UPDATE devices SET sampling_interval_seconds = 90 WHERE device_id = 'AMB-001';
COMMIT;

-- === ESCENARIO d: deadlock (B toma AIR-002 y pide AMB-001) ===

-- PASO 19 (B): después de que A bloqueó AMB-001 en el PASO 18. Bloquea AIR-002.
BEGIN;
UPDATE devices SET sampling_interval_seconds = 62 WHERE device_id = 'AIR-002';

-- PASO 21 (B): antes esperá a que la pestaña A haga el PASO 20 y quede ejecutando.
-- Pide AMB-001 y cierra el ciclo.
-- Si apareció ERROR "deadlock detected" (con los procesos y las filas involucradas),
-- B fue la víctima y su transacción está abortada; si no, la víctima fue A (miralo allí).
UPDATE devices SET sampling_interval_seconds = 62 WHERE device_id = 'AMB-001';

-- PASO 23 (B): después de que A cerró en el PASO 22. Cierra la transacción (si B fue la
-- víctima, COMMIT equivale a ROLLBACK).
-- Fin del laboratorio de concurrencia (pestaña B). La pestaña A restaura los valores en el PASO 24.
COMMIT;
RESET ROLE;
