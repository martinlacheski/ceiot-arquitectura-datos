\set ON_ERROR_STOP on

-- Monitoreo (clase 7, slides 54-55).
--
-- pg_stat_statements acumula, por consulta normalizada (sin valores literales),
-- cuántas veces corrió y cuánto tiempo total consumió. Requiere estar en
-- shared_preload_libraries (ver `command` del servicio postgres en compose.yaml)
-- y esta extensión en la base donde se la consulta.
--
-- No se otorga ningún permiso extra: lo consulta el dueño (ceiot) en
-- 05-monitoreo.sql. Los roles de aplicación (app_iot, ai_readonly, rag_*) no
-- deben ver el SQL de otras organizaciones: pg_stat_statements muestra el texto
-- de todas las consultas y por eso es una herramienta de administración.
--
-- Se puede volver a aplicar sobre una base ya creada:
--   psql -f /docker-entrypoint-initdb.d/08-monitoring.sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
