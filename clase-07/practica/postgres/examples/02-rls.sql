-- Row Level Security: aislamiento entre organizaciones (slides 23-29).
--
-- La política tenant_isolation compara organization_id con la variable de
-- sesión app.tenant_id. Este script usa el rol app_iot (sin privilegios de
-- administrador) y va cambiando el tenant para ver qué filas aparecen.
--
--   docker compose exec postgres sh -c \
--     'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /lab/examples/02-rls.sql'
--
-- Es repetible: las escrituras de la demo se hacen dentro de una transacción
-- que termina en ROLLBACK.
--
-- Desde pgAdmin: abrí el archivo (Open File → carpeta examples), seleccioná un
-- bloque y ejecutalo con F5; ejecutar todo el archivo muestra sólo el último resultado,
-- los avisos (NOTICE) aparecen en la pestaña Messages.
-- Las secciones a a f forman una sola transacción: seleccioná de BEGIN a ROLLBACK y
-- ejecutalas juntas (un BEGIN suelto deja la transacción abierta en la pestaña).

BEGIN;
SET ROLE app_iot;

-- === a. Sin contexto de tenant: 0 filas (la base falla cerrada) ===
RESET app.tenant_id;
SELECT count(*) AS equipos_sin_contexto FROM devices;

-- === b. Tenant 1 (Organización A): sólo sus equipos ===
SELECT set_config('app.tenant_id', '1', false);
SELECT organization_id, device_id, location_id FROM devices ORDER BY device_id;

-- === c. Tenant 2 (Organización B): sólo sus equipos ===
SELECT set_config('app.tenant_id', '2', false);
SELECT organization_id, device_id, location_id FROM devices ORDER BY device_id;

-- === d. Tenant 1 intenta mirar la organización 2 con un WHERE: 0 filas ===
-- El filtro del usuario se suma a la política; nunca la reemplaza.
SELECT set_config('app.tenant_id', '1', false);
SELECT count(*) AS equipos_de_la_org_2 FROM devices WHERE organization_id = 2;

-- === e. Tenant 1 intenta insertar una medición de la organización 2 ===
-- WITH CHECK rechaza la escritura: observá el aviso "Rechazado:".
DO $$
BEGIN
    INSERT INTO measurements (organization_id, device_id, measured_at, variable, value, unit, quality)
    VALUES (2, 'PLT-001', now(), 'temperature', 99, 'C', 'GOOD');
    RAISE NOTICE 'ATENCIÓN: el INSERT cruzado no debería haber funcionado';
EXCEPTION WHEN others THEN
    RAISE NOTICE 'Rechazado: %', SQLERRM;
END $$;

-- === f. Un INSERT de la propia organización sí funciona (se revierte al final) ===
INSERT INTO measurements (organization_id, device_id, measured_at, variable, value, unit, quality)
VALUES (1, 'AMB-001', now(), 'temperature', 22.5, 'C', 'GOOD');

ROLLBACK;
RESET ROLE;

-- === g. Como dueño/superusuario (ceiot): ve TODO, RLS no le aplica ===
-- Lección: la aplicación nunca debe conectarse como administrador.
SELECT current_user AS rol_actual, rolsuper AS es_superusuario, rolbypassrls AS saltea_rls
FROM pg_roles WHERE rolname = current_user;
SELECT organization_id, count(*) AS equipos FROM devices GROUP BY organization_id ORDER BY 1;
SELECT organization_id, count(*) AS mediciones FROM measurements GROUP BY organization_id ORDER BY 1;

-- === h. Qué tablas tienen RLS y qué políticas existen ===
-- pg_tables informa rowsecurity; FORCE vive en pg_class.relforcerowsecurity.
SELECT t.tablename, t.rowsecurity, c.relforcerowsecurity AS forcerowsecurity
FROM pg_tables AS t
JOIN pg_class AS c ON c.relname = t.tablename AND c.relnamespace = 'public'::regnamespace
WHERE t.schemaname = 'public'
ORDER BY t.tablename;

SELECT tablename, policyname, cmd, qual AS using_expr, with_check
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename, policyname;
