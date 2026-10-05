\set ON_ERROR_STOP on

-- Aislamiento entre organizaciones (tenants) con Row Level Security (RLS).
--
-- Idea: las tablas son compartidas y cada fila lleva organization_id. La base
-- compara esa columna con el valor de la variable de sesión app.tenant_id, que
-- la aplicación fija en cada transacción con set_config('app.tenant_id', ...).
-- Si la variable no está definida, NULLIF(..., '') la convierte en NULL, la
-- comparación nunca es verdadera y el resultado son 0 filas (falla cerrado).
--
-- Ojo: el superusuario (ceiot) ignora RLS aunque exista FORCE. Por eso la
-- aplicación nunca debe conectarse con ese rol.
--
-- Este archivo se puede volver a aplicar sobre una base ya creada:
--   psql -f /docker-entrypoint-initdb.d/07-tenant-rls.sql
BEGIN;

-- 1) Políticas por tabla ----------------------------------------------------
-- ENABLE activa RLS para los roles comunes; FORCE lo extiende también al dueño
-- de la tabla cuando no es superusuario (el superusuario sigue ignorándolo).
--
-- USING controla qué filas se VEN (SELECT) y cuáles se pueden tocar
--   (UPDATE/DELETE): una fila de otro tenant es invisible.
-- WITH CHECK controla qué filas se pueden ESCRIBIR (INSERT/UPDATE): impide
--   crear o mover una fila hacia otro tenant.
DO $policies$
DECLARE
    tabla text;
BEGIN
    FOREACH tabla IN ARRAY ARRAY[
        'organizations', 'locations', 'devices', 'measurements',
        'manual_documents', 'manual_chunks'
    ]
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', tabla);
        EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', tabla);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON public.%I', tabla);
        EXECUTE format(
            $policy$
            CREATE POLICY tenant_isolation ON public.%I
                FOR ALL
                USING (
                    organization_id = NULLIF(current_setting('app.tenant_id', true), '')::bigint
                )
                WITH CHECK (
                    organization_id = NULLIF(current_setting('app.tenant_id', true), '')::bigint
                )
            $policy$,
            tabla
        );
    END LOOP;
END
$policies$;

-- 2) Vistas lab_read ---------------------------------------------------------
-- Una vista normal se ejecuta con los permisos de su dueño (el superusuario),
-- que ignora RLS: sería una puerta trasera. security_invoker hace que la vista
-- se evalúe con los permisos (y las políticas) de quien la consulta.
ALTER VIEW lab_read.measurements SET (security_invoker = true);
ALTER VIEW lab_read.devices SET (security_invoker = true);
ALTER VIEW lab_read.locations SET (security_invoker = true);

-- 3) Roles de lectura: nunca pueden saltear RLS -------------------------------
ALTER ROLE ai_readonly NOBYPASSRLS;
ALTER ROLE rag_readonly NOBYPASSRLS;
ALTER ROLE rag_ingest NOBYPASSRLS;

-- 4) Rol de la aplicación IoT: mínimo privilegio ------------------------------
-- La contraseña fija es sólo para la demo local aislada.
DO $role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'app_iot') THEN
        CREATE ROLE app_iot
            LOGIN
            PASSWORD 'ceiot_app_iot_local_only'
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            NOREPLICATION
            NOBYPASSRLS;
    END IF;
END
$role$;

ALTER ROLE app_iot
    WITH LOGIN
    PASSWORD 'ceiot_app_iot_local_only'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOREPLICATION
    NOBYPASSRLS;
ALTER ROLE app_iot SET search_path = public, pg_catalog;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_iot;
REVOKE CREATE ON SCHEMA public FROM app_iot;
GRANT USAGE ON SCHEMA public TO app_iot;

-- Lectura de catálogos: la aplicación necesita saber qué equipos existen.
GRANT SELECT ON public.organizations, public.locations, public.devices TO app_iot;
-- Escritura de telemetría: sólo INSERT. No hay SELECT sobre measurements (no
-- hace falta para insertar, siempre que no se use INSERT ... RETURNING) ni DELETE
-- en ninguna tabla: una medición ya registrada no se borra desde la aplicación.
GRANT INSERT ON public.measurements TO app_iot;
-- Privilegio por columna: puede cambiar el intervalo de muestreo de un equipo
-- ("modificar determinadas configuraciones") pero ninguna otra columna.
GRANT UPDATE (sampling_interval_seconds) ON public.devices TO app_iot;

COMMIT;

-- current_database() no puede interpolarse dentro de GRANT/REVOKE. \gexec
-- aplica estas sentencias tanto durante init como al ejecutar el archivo a mano.
SELECT format(
    'REVOKE CREATE, TEMPORARY ON DATABASE %I FROM app_iot',
    current_database()
) \gexec
SELECT format(
    'GRANT CONNECT ON DATABASE %I TO app_iot',
    current_database()
) \gexec
