-- Error humano (slide 52): alguien borra datos por equivocación.
--
-- Orden del escenario:
--   1) sh /lab/examples/04-backup-restore.sh            (respaldo y restauración)
--   2) psql ... -f /lab/examples/04-error-humano.sql    (este archivo: el "accidente")
--   3) sh /lab/examples/04-backup-restore.sh recuperar  (rescate desde el respaldo)
--
--   docker compose --env-file .env -f compose.yaml exec postgres sh -c \
--     'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /lab/examples/04-error-humano.sql'
--
-- Se corre como dueño (ceiot): es el que tiene DELETE sobre measurements. La
-- aplicación (app_iot) no puede borrar mediciones: eso también es una defensa.
-- Importante: después del accidente NO vuelvas a correr el respaldo (paso 1):
-- sobrescribiría el dump bueno con los datos ya borrados.
--
-- Desde pgAdmin: abrí el archivo (Open File → Shared Storage → examples), seleccioná un
-- bloque y ejecutalo con F5; ejecutar todo el archivo muestra sólo el último resultado,
-- los avisos (NOTICE) aparecen en la pestaña Messages.

-- === Antes del accidente: mediciones por equipo ===
SELECT device_id, count(*) AS filas FROM measurements GROUP BY device_id ORDER BY 1;

-- === El accidente: DELETE sin cuidado sobre PLT-002 (organización B) ===
-- Qué observar: el DELETE confirma de inmediato; no hay "papelera" ni ROLLBACK posible.
DELETE FROM measurements WHERE device_id = 'PLT-002';

-- === Después: PLT-002 desapareció ===
SELECT device_id, count(*) AS filas FROM measurements GROUP BY device_id ORDER BY 1;
-- Siguiente paso: sh /lab/examples/04-backup-restore.sh recuperar
