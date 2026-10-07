-- Concurrencia (slides 40-47): PESTAÑA A de tres.
--
-- Hacen falta TRES pestañas de Query Tool en pgAdmin, todas sobre la base ceiot_class7
-- (Tools → Query Tool, o Alt+Shift+Q). Cada pestaña es una sesión distinta:
--
--   Pestaña A:  abrí este archivo (Open File → carpeta examples → 03-concurrencia-a.sql)
--   Pestaña B:  abrí 03-concurrencia-b.sql
--   Pestaña C:  abrí 03-concurrencia-observar.sql   (sólo se usa en el PASO 8)
--
-- Desde pgAdmin: en cada pestaña seleccioná UN bloque "-- PASO n" y ejecutalo con F5;
-- ejecutar todo el archivo no sirve acá, porque los pasos de A y B se intercalan. Los pasos
-- están numerados en TODO el laboratorio (1 a 24): seguí el orden de los números alternando
-- entre las pestañas A y B. Ejecutar un bloque muestra sólo el último resultado; los avisos
-- (NOTICE) y los errores aparecen en la pestaña Messages.
--
-- Cada paso usa BEGIN/COMMIT explícitos: la transacción queda abierta en la pestaña entre
-- un paso y el siguiente (pgAdmin muestra el estado de la transacción en la barra). Así
-- funciona con Auto commit activado, que es el valor por defecto. Un paso que "se cuelga"
-- (la pestaña queda ejecutando) está esperando un candado: pasá a la otra pestaña.
--
-- Alternativa sin pgAdmin: pegá los mismos bloques, en el mismo orden, en dos sesiones
-- interactivas de psql (docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER"
-- -d "$POSTGRES_DB"', sin -T). No se ejecuta con psql -f porque no hay pausas entre pasos.
--
-- Todo ocurre con el rol app_iot, tenant 1, sobre el equipo AMB-001 (y AIR-002 en el
-- escenario d): la columna sampling_interval_seconds, valor inicial 60.
-- Si algo queda a medias (cerraste una pestaña con una transacción abierta), ejecutá
-- ROLLBACK en esa pestaña y, como dueño (ceiot, superusuario), restaurá los valores:
--   UPDATE devices SET sampling_interval_seconds = 60;

-- PASO 0 (A): preparación de la pestaña A. Ejecutalo una vez, antes del PASO 1.
-- SET ROLE y el tenant se fijan FUERA de las transacciones: un ROLLBACK
-- también desharía un SET ROLE hecho dentro.
SET ROLE app_iot;
SELECT set_config('app.tenant_id', '1', false);

-- #############################################################
-- # ESCENARIO a: actualización perdida (lost update)          #
-- #############################################################
-- Qué observar: A y B leen 60, cada uno calcula su valor a partir de lo que
-- leyó y el segundo en escribir pisa el cambio del primero sin enterarse.

-- PASO 1 (A): abre la transacción y lee el valor. Resultado esperado: 60.
BEGIN;
SELECT sampling_interval_seconds AS leido FROM devices WHERE device_id = 'AMB-001';

-- PASO 3 (A): después de que B leyó en el PASO 2. Escribí el valor que leíste en el
-- PASO 1 menos 30 (60 - 30 = 30) y confirmá.
UPDATE devices SET sampling_interval_seconds = 30 WHERE device_id = 'AMB-001';
COMMIT;
-- A confirmó 30. Ahora B (PASO 4) escribirá 120 basándose en su lectura vieja.

-- PASO 5 (A): después de que B confirmó en el PASO 4. Resultado esperado: 120.
-- Observá: el valor final es 120 (el último en escribir). El 30 de A se perdió
-- sin ningún error.
SELECT sampling_interval_seconds AS valor_final FROM devices WHERE device_id = 'AMB-001';
-- Restauramos 60 para el escenario siguiente (seleccioná y ejecutá sólo esta línea):
UPDATE devices SET sampling_interval_seconds = 60 WHERE device_id = 'AMB-001';

-- #############################################################
-- # ESCENARIO b: SELECT ... FOR UPDATE (bloqueo pesimista)    #
-- #############################################################
-- Qué observar: B queda ESPERANDO (su pestaña queda ejecutando) hasta que A
-- confirma; entonces B lee el valor NUEVO y no pisa nada.

-- PASO 6 (A): toma el bloqueo de la fila. Resultado esperado: 60.
BEGIN;
SELECT sampling_interval_seconds AS leido FROM devices WHERE device_id = 'AMB-001' FOR UPDATE;
-- A tiene la fila bloqueada. Ahora B hace el PASO 7 y se bloquea.
-- PASO 8: en la pestaña C ejecutá 03-concurrencia-observar.sql mientras B espera.
--         En pgAdmin: base ceiot_class7 > pestaña Dashboard > Sessions / Locks.

-- PASO 9 (A): con B esperando. Escribí el valor que leíste en el PASO 6 menos 30
-- (60 - 30 = 30) y confirmá.
UPDATE devices SET sampling_interval_seconds = 30 WHERE device_id = 'AMB-001';
COMMIT;
-- A confirmó 30: la pestaña B se destraba sola y lee 30 (no 60).

-- PASO 11 (A): después de que B confirmó en el PASO 10. Resultado esperado: 40.
-- Observá: 40 = 60 - 30 (A) + 10 (B). Se aplicaron los dos cambios.
SELECT sampling_interval_seconds AS valor_final FROM devices WHERE device_id = 'AMB-001';
-- Restauramos 60 (seleccioná y ejecutá sólo esta línea):
UPDATE devices SET sampling_interval_seconds = 60 WHERE device_id = 'AMB-001';

-- #############################################################
-- # ESCENARIO c: REPEATABLE READ (falla en vez de perder)     #
-- #############################################################
-- Qué observar: B recibe "could not serialize access due to concurrent update"
-- en lugar de pisar el cambio de A; la aplicación debe reintentar.

-- PASO 12 (A): abre la transacción REPEATABLE READ y lee. Resultado esperado: 60.
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT sampling_interval_seconds AS leido FROM devices WHERE device_id = 'AMB-001';

-- PASO 14 (A): después de que B leyó en el PASO 13. Escribí el valor que leíste en el
-- PASO 12 menos 30 (60 - 30 = 30) y confirmá.
UPDATE devices SET sampling_interval_seconds = 30 WHERE device_id = 'AMB-001';
COMMIT;
-- A confirmó 30. En el PASO 15 B intentará escribir con su lectura vieja.

-- PASO 17 (A): después de que B reintentó en el PASO 16. Resultado esperado: 90.
-- Observá: 90 = 60 - 30 (A) + 60 (B reintentado sobre el 30 de A). Nada se perdió.
SELECT sampling_interval_seconds AS valor_final FROM devices WHERE device_id = 'AMB-001';
-- Restauramos 60 (seleccioná y ejecutá sólo esta línea):
UPDATE devices SET sampling_interval_seconds = 60 WHERE device_id = 'AMB-001';

-- #############################################################
-- # ESCENARIO d: deadlock (bloqueo mutuo)                     #
-- #############################################################
-- Qué observar: A toma AMB-001 y quiere AIR-002; B toma AIR-002 y quiere
-- AMB-001. PostgreSQL detecta el ciclo tras deadlock_timeout (1 s) y aborta
-- una de las dos con "deadlock detected". Casi siempre es B (la que cierra
-- el ciclo); si ejecutás el PASO 21 muy rápido después del PASO 20 puede ser A.
SHOW deadlock_timeout;

-- PASO 18 (A): bloquea AMB-001.
BEGIN;
UPDATE devices SET sampling_interval_seconds = 61 WHERE device_id = 'AMB-001';

-- PASO 20 (A): después de que B bloqueó AIR-002 en el PASO 19. Pide AIR-002: esta pestaña
-- queda ejecutando, esperando el candado de B. Pasá enseguida a la pestaña B (PASO 21).
UPDATE devices SET sampling_interval_seconds = 61 WHERE device_id = 'AIR-002';
-- Si el UPDATE anterior falló con "deadlock detected", A fue la víctima: su transacción
-- quedó abortada. Si terminó bien, B fue la víctima y A ya tiene las dos filas.

-- PASO 22 (A): después del PASO 21 de B. Cierra la transacción (si A fue la víctima,
-- COMMIT equivale a ROLLBACK).
COMMIT;

-- PASO 24 (A): después de que B cerró en el PASO 23. Restaura los dos equipos.
-- Resultado esperado: ambos vuelven a 60. Fin del laboratorio (pestaña A).
UPDATE devices SET sampling_interval_seconds = 60 WHERE device_id IN ('AMB-001', 'AIR-002');
SELECT device_id, sampling_interval_seconds FROM devices WHERE device_id IN ('AMB-001', 'AIR-002') ORDER BY device_id;
RESET ROLE;
