\set ON_ERROR_STOP on
\pset pager off
\set ECHO queries

-- Concurrencia (slides 40-47): TERMINAL A de tres.
--
-- Hacen falta TRES terminales con la pila levantada. Con psql interactivo
-- (el comando "exec" abre una terminal, no usar -T):
--
--   Terminal A:  docker compose --env-file .env -f compose.yaml exec postgres sh -c \
--                  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /lab/examples/03-concurrencia-a.sql'
--   Terminal B:  ... -f /lab/examples/03-concurrencia-b.sql     (mismo comando, otro archivo)
--   Terminal C:  ... -f /lab/examples/03-concurrencia-observar.sql  (sólo en el paso 8)
--
-- Los pasos están numerados en TODO el laboratorio (1 a 24) y cada terminal
-- sólo ejecuta los que le tocan: antes de cada paso aparece una pausa
-- (\prompt) y vos decidís cuándo apretar Enter. Seguí el orden de los números,
-- alternando entre las terminales A y B. (\prompt no existe en pgAdmin: este
-- laboratorio es sólo para psql.)
--
-- Todo ocurre con el rol app_iot, tenant 1, sobre el equipo AMB-001 (y AIR-002
-- en el escenario d): la columna sampling_interval_seconds, valor inicial 60.
-- Si algo queda a medias (cerraste una terminal con una transacción abierta),
-- el dueño restaura los valores con:
--   UPDATE devices SET sampling_interval_seconds = 60;   -- como ceiot (superusuario)

SET ROLE app_iot;
SELECT set_config('app.tenant_id', '1', false);
-- SET ROLE y el tenant se fijan FUERA de las transacciones: un ROLLBACK
-- también desharía un SET ROLE hecho dentro.

\echo
\echo '#############################################################'
\echo '# ESCENARIO a: actualización perdida (lost update)         #'
\echo '#############################################################'
\echo 'Qué observar: A y B leen 60, cada uno calcula su valor a partir de lo que'
\echo 'leyó y el segundo en escribir pisa el cambio del primero sin enterarse.'

\prompt 'PASO 1 (terminal A): Enter para leer el valor...' paso
BEGIN;
SELECT sampling_interval_seconds AS leido FROM devices WHERE device_id = 'AMB-001' \gset
\echo 'A leyó' :leido '(A calculará leído - 30 = 30)'

\prompt 'PASO 3 (terminal A, luego de que B haya leído en el paso 2): Enter para escribir y confirmar...' paso
UPDATE devices SET sampling_interval_seconds = :leido - 30 WHERE device_id = 'AMB-001';
COMMIT;
\echo 'A confirmó 30. Ahora B (paso 4) escribirá 120 basándose en su lectura vieja.'

\prompt 'PASO 5 (terminal A, luego de que B confirmó en el paso 4): Enter para ver el resultado...' paso
SELECT sampling_interval_seconds AS valor_final FROM devices WHERE device_id = 'AMB-001';
\echo 'Observá: el valor final es 120 (el último en escribir). El 30 de A se perdió'
\echo 'sin ningún error. Restauramos 60 para el escenario siguiente.'
UPDATE devices SET sampling_interval_seconds = 60 WHERE device_id = 'AMB-001';

\echo
\echo '#############################################################'
\echo '# ESCENARIO b: SELECT ... FOR UPDATE (bloqueo pesimista)    #'
\echo '#############################################################'
\echo 'Qué observar: B queda ESPERANDO (la terminal "se cuelga") hasta que A'
\echo 'confirma; entonces B lee el valor NUEVO y no pisa nada.'

\prompt 'PASO 6 (terminal A): Enter para tomar el bloqueo de la fila...' paso
BEGIN;
SELECT sampling_interval_seconds AS leido FROM devices WHERE device_id = 'AMB-001' FOR UPDATE \gset
\echo 'A tiene la fila bloqueada (leyó' :leido '). Ahora B hace el paso 7 y se bloquea.'
\echo 'PASO 8: en la terminal C corré 03-concurrencia-observar.sql mientras B espera.'
\echo '        En pgAdmin: base ceiot_class7 > pestaña Dashboard > Sessions / Locks.'

\prompt 'PASO 9 (terminal A, con B esperando): Enter para escribir y confirmar...' paso
UPDATE devices SET sampling_interval_seconds = :leido - 30 WHERE device_id = 'AMB-001';
COMMIT;
\echo 'A confirmó 30: la terminal B se destraba sola y lee 30 (no 60).'

\prompt 'PASO 11 (terminal A, luego de que B confirmó en el paso 10): Enter para ver el resultado...' paso
SELECT sampling_interval_seconds AS valor_final FROM devices WHERE device_id = 'AMB-001';
\echo 'Observá: 40 = 60 - 30 (A) + 10 (B). Se aplicaron los dos cambios.'
UPDATE devices SET sampling_interval_seconds = 60 WHERE device_id = 'AMB-001';

\echo
\echo '#############################################################'
\echo '# ESCENARIO c: REPEATABLE READ (falla en vez de perder)     #'
\echo '#############################################################'
\echo 'Qué observar: B recibe "could not serialize access due to concurrent update"'
\echo 'en lugar de pisar el cambio de A; la aplicación debe reintentar.'

\prompt 'PASO 12 (terminal A): Enter para abrir la transacción REPEATABLE READ y leer...' paso
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT sampling_interval_seconds AS leido FROM devices WHERE device_id = 'AMB-001' \gset
\echo 'A leyó' :leido

\prompt 'PASO 14 (terminal A, luego de que B leyó en el paso 13): Enter para escribir y confirmar...' paso
UPDATE devices SET sampling_interval_seconds = :leido - 30 WHERE device_id = 'AMB-001';
COMMIT;
\echo 'A confirmó 30. En el paso 15 B intentará escribir con su lectura vieja.'

\prompt 'PASO 17 (terminal A, luego de que B reintentó en el paso 16): Enter para ver el resultado...' paso
SELECT sampling_interval_seconds AS valor_final FROM devices WHERE device_id = 'AMB-001';
\echo 'Observá: 90 = 60 - 30 (A) + 60 (B reintentado). Nada se perdió.'
UPDATE devices SET sampling_interval_seconds = 60 WHERE device_id = 'AMB-001';

\echo
\echo '#############################################################'
\echo '# ESCENARIO d: deadlock (bloqueo mutuo)                     #'
\echo '#############################################################'
\echo 'Qué observar: A toma AMB-001 y quiere AIR-002; B toma AIR-002 y quiere'
\echo 'AMB-001. PostgreSQL detecta el ciclo tras deadlock_timeout (1 s) y aborta'
\echo 'una de las dos con "deadlock detected". Casi siempre es B (la que cierra'
\echo 'el ciclo); si apretás muy rápido Enter en el paso 21 puede ser A.'
SHOW deadlock_timeout;
-- A partir de acá se esperan errores: no cortamos el script.
\set ON_ERROR_STOP off

\prompt 'PASO 18 (terminal A): Enter para bloquear AMB-001...' paso
BEGIN;
UPDATE devices SET sampling_interval_seconds = 61 WHERE device_id = 'AMB-001';

\prompt 'PASO 20 (terminal A, luego de que B bloqueó AIR-002 en el paso 19): Enter para pedir AIR-002 (va a esperar)...' paso
UPDATE devices SET sampling_interval_seconds = 61 WHERE device_id = 'AIR-002';

\echo 'Si el UPDATE anterior falló con "deadlock detected", A fue la víctima: su transacción'
\echo 'quedó abortada. Si terminó bien, B fue la víctima y A ya tiene las dos filas.'
\prompt 'PASO 22 (terminal A, luego del paso 21 de B): Enter para cerrar la transacción...' paso
COMMIT;

\prompt 'PASO 24 (terminal A, luego de que B cerró en el paso 23): Enter para restaurar los valores...' paso
\set ON_ERROR_STOP on
UPDATE devices SET sampling_interval_seconds = 60 WHERE device_id IN ('AMB-001', 'AIR-002');
SELECT device_id, sampling_interval_seconds FROM devices WHERE device_id IN ('AMB-001', 'AIR-002') ORDER BY device_id;
\echo 'Listo: ambos equipos vuelven a 60. Fin del laboratorio de concurrencia (terminal A).'
RESET ROLE;
