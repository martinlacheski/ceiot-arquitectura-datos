\set ON_ERROR_STOP on

-- Frontera didáctica para Text-to-SQL. La contraseña fija de abajo es sólo
-- para la demo local aislada; no es una credencial apta para producción.
BEGIN;

CREATE SCHEMA IF NOT EXISTS lab_read;
REVOKE ALL ON SCHEMA lab_read FROM PUBLIC;
-- Esta base está dedicada al laboratorio: PUBLIC no debe habilitar acceso al
-- esquema de aplicación ni permitir crear objetos que alteren el search_path.
REVOKE USAGE, CREATE ON SCHEMA public FROM PUBLIC;

-- location_id y organization_id se agregan al final: CREATE OR REPLACE VIEW no puede reordenar
-- columnas existentes, sólo puede anexar nuevas al final de la lista.
CREATE OR REPLACE VIEW lab_read.measurements
WITH (security_barrier = true)
AS
SELECT
    measurement.device_id,
    measurement.measured_at,
    measurement.variable,
    measurement.value,
    measurement.unit,
    measurement.quality,
    device.location_id,
    measurement.organization_id
FROM public.measurements AS measurement
JOIN public.devices AS device ON device.device_id = measurement.device_id;

CREATE OR REPLACE VIEW lab_read.devices
WITH (security_barrier = true)
AS
SELECT
    device_id,
    model,
    location_id,
    depends_on_device_id,
    organization_id
FROM public.devices;

CREATE OR REPLACE VIEW lab_read.locations
WITH (security_barrier = true)
AS
SELECT
    location_id,
    name,
    building,
    organization_id
FROM public.locations;

REVOKE ALL ON lab_read.measurements, lab_read.devices, lab_read.locations FROM PUBLIC;

DO $role$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'ai_readonly'
    ) THEN
        CREATE ROLE ai_readonly
            LOGIN
            PASSWORD 'ceiot_ai_readonly_local_only'
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            NOREPLICATION
            NOBYPASSRLS;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'rag_readonly'
    ) THEN
        -- Contraseña fija exclusivamente para la demo local aislada.
        CREATE ROLE rag_readonly
            LOGIN
            PASSWORD 'ceiot_rag_readonly_demo_only'
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            NOREPLICATION
            NOBYPASSRLS;
    END IF;
END
$role$;

-- Reaplicar estos atributos vuelve idempotente la configuración si el rol ya
-- existía. Nunca usar el propietario de la base para ejecutar SQL generado.
ALTER ROLE ai_readonly
    WITH LOGIN
    PASSWORD 'ceiot_ai_readonly_local_only'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOREPLICATION
    NOBYPASSRLS;
ALTER ROLE ai_readonly SET search_path = pg_catalog;
ALTER ROLE ai_readonly SET default_transaction_read_only = on;
ALTER ROLE ai_readonly SET statement_timeout = '2000ms';
ALTER ROLE ai_readonly SET lock_timeout = '500ms';
ALTER ROLE ai_readonly SET idle_in_transaction_session_timeout = '3000ms';

ALTER ROLE rag_readonly
    WITH LOGIN
    PASSWORD 'ceiot_rag_readonly_demo_only'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOREPLICATION
    NOBYPASSRLS;
ALTER ROLE rag_readonly SET search_path = public, pg_catalog;
ALTER ROLE rag_readonly SET default_transaction_read_only = on;
ALTER ROLE rag_readonly SET statement_timeout = '2000ms';
ALTER ROLE rag_readonly SET lock_timeout = '500ms';
ALTER ROLE rag_readonly SET idle_in_transaction_session_timeout = '3000ms';

REVOKE ALL ON SCHEMA public FROM ai_readonly;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ai_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON TABLES FROM ai_readonly;
GRANT USAGE ON SCHEMA lab_read TO ai_readonly;
GRANT SELECT ON lab_read.measurements, lab_read.devices, lab_read.locations TO ai_readonly;

REVOKE ALL ON SCHEMA lab_read FROM rag_readonly;
REVOKE ALL ON SCHEMA public FROM rag_readonly;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM rag_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON TABLES FROM rag_readonly;
GRANT USAGE ON SCHEMA public TO rag_readonly;
GRANT SELECT ON public.manual_chunks, public.manual_documents TO rag_readonly;

COMMIT;

-- current_database() no puede interpolarse dentro de GRANT/REVOKE. \gexec
-- aplica estas sentencias tanto durante init como al ejecutar el archivo a mano.
SELECT format(
    'REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC',
    current_database()
) \gexec
SELECT format(
    'REVOKE CREATE, TEMPORARY ON DATABASE %I FROM ai_readonly',
    current_database()
) \gexec
SELECT format(
    'GRANT CONNECT ON DATABASE %I TO ai_readonly',
    current_database()
) \gexec
SELECT format(
    'REVOKE CREATE, TEMPORARY ON DATABASE %I FROM rag_readonly',
    current_database()
) \gexec
SELECT format(
    'GRANT CONNECT ON DATABASE %I TO rag_readonly',
    current_database()
) \gexec
