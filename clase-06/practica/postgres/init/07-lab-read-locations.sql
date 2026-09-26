\set ON_ERROR_STOP on

-- Evolución idempotente que expone location_id en lab_read.measurements y
-- agrega lab_read.locations para que Text-to-SQL pueda filtrar por aula
-- (filminas de la Clase 6). Requiere que 06-locations.sql ya haya creado
-- public.locations y la FK devices.location_id. Aplicable tanto durante la
-- inicialización de un volumen fresco (04-ai-views.sql ya define esta forma)
-- como a mano sobre un volumen existente.
BEGIN;

-- location_id se agrega al final: CREATE OR REPLACE VIEW no puede reordenar
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
    device.location_id
FROM public.measurements AS measurement
JOIN public.devices AS device ON device.device_id = measurement.device_id;

CREATE OR REPLACE VIEW lab_read.locations
WITH (security_barrier = true)
AS
SELECT
    location_id,
    name,
    building
FROM public.locations;

REVOKE ALL ON lab_read.measurements, lab_read.devices, lab_read.locations FROM PUBLIC;
GRANT SELECT ON lab_read.measurements, lab_read.devices, lab_read.locations TO ai_readonly;

COMMIT;
