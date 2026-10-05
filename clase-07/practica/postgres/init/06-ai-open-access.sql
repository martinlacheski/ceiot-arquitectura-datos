\set ON_ERROR_STOP on

-- Text-to-SQL abierto: la frontera de seguridad es la base de datos.
--
-- ai_readonly puede leer todas las tablas del esquema public y nada más:
-- no puede escribir (sin privilegios y con transacciones de sólo lectura),
-- no puede crear objetos ni tablas temporales y tiene timeouts cortos.
-- El modelo descubre el esquema consultando el catálogo con este mismo rol,
-- así que lo que ve es exactamente lo que puede leer.
--
-- Este archivo también se puede aplicar a una base ya creada:
--   psql -f /docker-entrypoint-initdb.d/06-ai-open-access.sql
BEGIN;

-- Documentar la base en la base: estos comentarios llegan al modelo como
-- parte del esquema descubierto (obj_description / col_description).
COMMENT ON TABLE public.locations IS 'Ubicaciones físicas (aulas, laboratorios, sedes)';
COMMENT ON COLUMN public.locations.position IS 'Punto geográfico PostGIS (geography, SRID 4326); ST_Distance devuelve metros';
COMMENT ON TABLE public.devices IS 'Sensores y actuadores IoT instalados en una ubicación';
COMMENT ON COLUMN public.devices.model IS 'Modelo comercial del equipo, por ejemplo ENV-X';
COMMENT ON COLUMN public.devices.position IS 'Punto geográfico PostGIS (geography, SRID 4326); ST_Distance devuelve metros';
COMMENT ON COLUMN public.devices.depends_on_device_id IS 'Equipo del que depende este equipo, si existe';
COMMENT ON TABLE public.measurements IS 'Historial de mediciones (hypertable TimescaleDB particionada por measured_at)';
COMMENT ON COLUMN public.measurements.variable IS 'Magnitud medida; los valores distinguen mayúsculas y minúsculas';
COMMENT ON COLUMN public.measurements.value IS 'Valor medido, expresado en la unidad de la columna unit';
COMMENT ON COLUMN public.measurements.quality IS 'Calidad del dato: GOOD, SUSPECT o BAD';
COMMENT ON TABLE public.manual_documents IS 'Manuales y PDF cargados (metadatos; el archivo vive en S3)';
COMMENT ON TABLE public.manual_chunks IS 'Fragmentos de texto de los PDF con su embedding (pgvector)';
COMMENT ON COLUMN public.manual_chunks.embedding IS 'Embedding de 1024 dimensiones; distancia coseno con el operador <=>';

-- Reemplaza el acceso por vistas lab_read de 04-ai-views.sql.
REVOKE ALL ON ALL TABLES IN SCHEMA lab_read FROM ai_readonly;
REVOKE ALL ON SCHEMA lab_read FROM ai_readonly;

GRANT USAGE ON SCHEMA public TO ai_readonly;
REVOKE CREATE ON SCHEMA public FROM ai_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ai_readonly;

ALTER ROLE ai_readonly SET search_path = public, pg_catalog;

COMMIT;

-- Estadísticas frescas: pg_stats alimenta los valores frecuentes del esquema.
ANALYZE;
