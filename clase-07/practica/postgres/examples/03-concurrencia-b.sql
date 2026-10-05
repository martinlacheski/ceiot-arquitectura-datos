\set ON_ERROR_STOP on
\pset pager off
\set ECHO queries

-- Concurrencia (slides 40-47): TERMINAL B de tres.
--
-- Corré este archivo en la segunda terminal, igual que el de la terminal A
-- (ver 03-concurrencia-a.sql para el comando completo y la explicación):
--
--   docker compose --env-file .env -f compose.yaml exec postgres sh -c \
--     'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /lab/examples/03-concurrencia-b.sql'
--
-- Los pasos tienen la misma numeración global (1 a 24). Esta terminal ejecuta
-- los pares: 2, 4, 7, 10, 13, 15, 16, 19, 21 y 23. Apretá Enter en cada pausa
-- sólo cuando la terminal A haya terminado el paso anterior.

SET ROLE app_iot;
SELECT set_config('app.tenant_id', '1', false);

\echo
\echo '=== ESCENARIO a: actualización perdida (B es la que pisa) ==='

\prompt 'PASO 2 (terminal B, luego de que A leyó en el paso 1): Enter para leer el valor...' paso
BEGIN;
SELECT sampling_interval_seconds AS leido FROM devices WHERE device_id = 'AMB-001' \gset
\echo 'B también leyó' :leido '(A todavía no confirmó nada de lo que viene)'

\prompt 'PASO 4 (terminal B, luego de que A confirmó en el paso 3): Enter para escribir leído + 60 y confirmar...' paso
UPDATE devices SET sampling_interval_seconds = :leido + 60 WHERE device_id = 'AMB-001';
COMMIT;
\echo 'B confirmó 120 usando su lectura vieja (60): sobreescribió el 30 de A sin error.'

\echo
\echo '=== ESCENARIO b: SELECT ... FOR UPDATE (B espera a A) ==='

\prompt 'PASO 7 (terminal B, luego de que A tomó el bloqueo en el paso 6): Enter para pedir el mismo bloqueo...' paso
BEGIN;
\echo 'Ahora esta terminal se queda ESPERANDO: la fila está bloqueada por A.'
\echo 'Andá a la terminal C (paso 8) y después a la A (paso 9).'
SELECT sampling_interval_seconds AS leido FROM devices WHERE device_id = 'AMB-001' FOR UPDATE \gset
\echo 'B se destrabó. Leyó' :leido '(el valor que dejó A, no el 60 original).'

\prompt 'PASO 10 (terminal B): Enter para escribir leído + 10 y confirmar...' paso
UPDATE devices SET sampling_interval_seconds = :leido + 10 WHERE device_id = 'AMB-001';
COMMIT;
\echo 'B confirmó 40. Ahora A muestra el resultado en el paso 11.'

\echo
\echo '=== ESCENARIO c: REPEATABLE READ (B recibe un error de serialización) ==='

\prompt 'PASO 13 (terminal B, luego de que A leyó en el paso 12): Enter para abrir la transacción REPEATABLE READ y leer...' paso
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT sampling_interval_seconds AS leido FROM devices WHERE device_id = 'AMB-001' \gset
\echo 'B leyó' :leido

-- El error del paso 15 es lo que queremos ver: no cortamos el script.
\set ON_ERROR_STOP off
\prompt 'PASO 15 (terminal B, luego de que A confirmó en el paso 14): Enter para intentar escribir leído + 60...' paso
UPDATE devices SET sampling_interval_seconds = :leido + 60 WHERE device_id = 'AMB-001';
\echo 'Observá: ERROR "could not serialize access due to concurrent update".'
\echo 'En vez de pisar el 30 de A, PostgreSQL rechaza la escritura. La transacción quedó abortada.'
ROLLBACK;
\set ON_ERROR_STOP on

\prompt 'PASO 16 (terminal B): Enter para REINTENTAR la transacción completa...' paso
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT sampling_interval_seconds AS leido FROM devices WHERE device_id = 'AMB-001' \gset
UPDATE devices SET sampling_interval_seconds = :leido + 60 WHERE device_id = 'AMB-001';
COMMIT;
\echo 'El reintento leyó' :leido 'y escribió' :leido '+ 60. Ahora A muestra el resultado en el paso 17.'

\echo
\echo '=== ESCENARIO d: deadlock (B toma AIR-002 y pide AMB-001) ==='
\set ON_ERROR_STOP off

\prompt 'PASO 19 (terminal B, luego de que A bloqueó AMB-001 en el paso 18): Enter para bloquear AIR-002...' paso
BEGIN;
UPDATE devices SET sampling_interval_seconds = 62 WHERE device_id = 'AIR-002';

\echo 'Antes del paso 21 esperá a que la terminal A haga el paso 20 y quede esperando.'
\prompt 'PASO 21 (terminal B): Enter para pedir AMB-001 y cerrar el ciclo...' paso
UPDATE devices SET sampling_interval_seconds = 62 WHERE device_id = 'AMB-001';
\echo 'Si apareció ERROR "deadlock detected" (con los procesos y las filas involucradas),'
\echo 'B fue la víctima y su transacción está abortada; si no, la víctima fue A (miralo allí).'

\prompt 'PASO 23 (terminal B, luego de que A cerró en el paso 22): Enter para cerrar la transacción...' paso
COMMIT;
\set ON_ERROR_STOP on
\echo 'Fin del laboratorio de concurrencia (terminal B). La terminal A restaura los valores en el paso 24.'
RESET ROLE;
