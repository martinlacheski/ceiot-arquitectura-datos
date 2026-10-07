-- Roles y mínimo privilegio (slides 8-14).
--
-- Se ejecuta como el dueño (ceiot) y cambia de identidad con SET ROLE para ver
-- qué puede y qué no puede hacer cada rol. Los rechazos se capturan dentro de
-- DO ... EXCEPTION para que el script siga y muestre el mensaje de la base.
--
--   docker compose exec postgres sh -c \
--     'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /lab/examples/01-roles-permisos.sql'
--
-- Es repetible: las escrituras de la demo se deshacen con ROLLBACK.
--
-- Desde pgAdmin: abrí el archivo (Open File → carpeta examples), seleccioná un
-- bloque y ejecutalo con F5; ejecutar todo el archivo muestra sólo el último resultado,
-- los avisos (NOTICE) aparecen en la pestaña Messages.
-- Las secciones 3 y 4 forman una sola transacción: seleccioná de BEGIN a ROLLBACK y
-- ejecutalas juntas (un BEGIN suelto deja la transacción abierta en la pestaña).

-- === 1. Matriz de privilegios: qué puede hacer cada rol sobre cada tabla ===
-- Observá: app_iot sólo lee catálogos e inserta mediciones; ai_readonly sólo lee.
-- Ningún rol tiene DELETE.
SELECT
    r.rol,
    t.tabla,
    has_table_privilege(r.rol, 'public.' || t.tabla, 'SELECT') AS "select",
    has_table_privilege(r.rol, 'public.' || t.tabla, 'INSERT') AS "insert",
    has_table_privilege(r.rol, 'public.' || t.tabla, 'UPDATE') AS "update",
    has_table_privilege(r.rol, 'public.' || t.tabla, 'DELETE') AS "delete"
FROM (VALUES ('app_iot'), ('ai_readonly')) AS r (rol)
CROSS JOIN (VALUES ('organizations'), ('locations'), ('devices'), ('measurements')) AS t (tabla)
ORDER BY r.rol, t.tabla;

-- === 2. Privilegio por columna: app_iot sólo puede actualizar sampling_interval_seconds ===
SELECT
    has_column_privilege('app_iot', 'public.devices', 'sampling_interval_seconds', 'UPDATE') AS "puede cambiar sampling_interval_seconds",
    has_column_privilege('app_iot', 'public.devices', 'model', 'UPDATE') AS "puede cambiar model";

-- === 3. Como app_iot (tenant 1): lectura e inserción permitidas ===
-- Observá: el SELECT devuelve los equipos de la organización 1 y el INSERT dice INSERT 0 1.
BEGIN;
SET ROLE app_iot;
SELECT set_config('app.tenant_id', '1', false);
SELECT current_user AS rol_actual, current_setting('app.tenant_id') AS tenant;
SELECT device_id, model, location_id FROM devices ORDER BY device_id;

-- Inserta una medición de demostración; el ROLLBACK final la descarta.
INSERT INTO measurements (organization_id, device_id, measured_at, variable, value, unit, quality)
VALUES (1, 'AMB-001', now(), 'temperature', 22.5, 'C', 'GOOD');

-- Cambiar el intervalo de muestreo (columna permitida).
UPDATE devices SET sampling_interval_seconds = 30 WHERE device_id = 'AMB-001';

-- === 4. Operaciones que la base rechaza (se muestra el mensaje) ===
-- Observá los avisos "Rechazado:": son el mínimo privilegio en acción.
DO $$
BEGIN
    DELETE FROM measurements WHERE device_id = 'AMB-001';
    RAISE NOTICE 'ATENCIÓN: el DELETE no debería haber funcionado';
EXCEPTION WHEN others THEN
    RAISE NOTICE 'Rechazado (DELETE en measurements): %', SQLERRM;
END $$;

DO $$
BEGIN
    CREATE TABLE tabla_pirata (id int);
    RAISE NOTICE 'ATENCIÓN: el CREATE TABLE no debería haber funcionado';
EXCEPTION WHEN others THEN
    RAISE NOTICE 'Rechazado (CREATE TABLE): %', SQLERRM;
END $$;

DO $$
BEGIN
    UPDATE devices SET model = 'HACK' WHERE device_id = 'AMB-001';
    RAISE NOTICE 'ATENCIÓN: el UPDATE de model no debería haber funcionado';
EXCEPTION WHEN others THEN
    RAISE NOTICE 'Rechazado (UPDATE de otra columna): %', SQLERRM;
END $$;

DO $$
BEGIN
    PERFORM count(*) FROM measurements;
    RAISE NOTICE 'ATENCIÓN: app_iot no debería poder leer measurements';
EXCEPTION WHEN others THEN
    RAISE NOTICE 'Rechazado (SELECT en measurements): %', SQLERRM;
END $$;

-- Deshace la medición y el cambio de muestreo de la demostración.
ROLLBACK;
RESET ROLE;

-- === 5. Como ai_readonly: sólo lectura ===
BEGIN;
SET ROLE ai_readonly;
SELECT set_config('app.tenant_id', '1', false);
SELECT count(*) AS equipos_visibles FROM devices;
DO $$
BEGIN
    DELETE FROM devices;
    RAISE NOTICE 'ATENCIÓN: el DELETE no debería haber funcionado';
EXCEPTION WHEN others THEN
    RAISE NOTICE 'Rechazado (DELETE como ai_readonly): %', SQLERRM;
END $$;
ROLLBACK;
RESET ROLE;

-- === Fin: identidad restaurada ===
SELECT current_user AS rol_actual;
