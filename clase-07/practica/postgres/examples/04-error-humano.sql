\set ON_ERROR_STOP on

-- Error humano (slide 52): alguien borra datos por equivocación.
--
-- Orden del escenario:
--   1) sh /lab/examples/04-backup-restore.sh            (respaldo y restauración)
--   2) psql ... -f /lab/examples/04-error-humano.sql    (este archivo: el "accidente")
--   3) sh /lab/examples/04-backup-restore.sh recuperar  (rescate desde el respaldo)
--
--   docker compose --env-file .env -f compose.yaml exec postgres sh -c \
--     'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /lab/examples/04-error-humano.sql'
--
-- Se corre como dueño (ceiot): es el que tiene DELETE sobre measurements. La
-- aplicación (app_iot) no puede borrar mediciones: eso también es una defensa.
-- Importante: después del accidente NO vuelvas a correr el respaldo (paso 1):
-- sobrescribiría el dump bueno con los datos ya borrados.

\echo
\echo '=== Antes del accidente: mediciones por equipo ==='
SELECT device_id, count(*) AS filas FROM measurements GROUP BY device_id ORDER BY 1;

\echo
\echo '=== El accidente: DELETE sin cuidado sobre PLT-002 (organización B) ==='
\echo 'Qué observar: el DELETE confirma de inmediato; no hay "papelera" ni ROLLBACK posible.'
DELETE FROM measurements WHERE device_id = 'PLT-002';

\echo
\echo '=== Después: PLT-002 desapareció ==='
SELECT device_id, count(*) AS filas FROM measurements GROUP BY device_id ORDER BY 1;
\echo
\echo 'Siguiente paso: sh /lab/examples/04-backup-restore.sh recuperar'
