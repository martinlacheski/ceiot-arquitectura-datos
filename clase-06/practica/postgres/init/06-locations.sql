\set ON_ERROR_STOP on

-- Evolución idempotente que agrega ubicaciones geográficas para dispositivos
-- y mediciones (alineación con las filminas de la Clase 6: Aula 204, ENV-X).
-- Aplicable tanto durante la inicialización de un volumen fresco (02-schema.sql
-- ya crea locations antes que devices) como a mano sobre un volumen existente.
BEGIN;

CREATE TABLE IF NOT EXISTS public.locations (
    location_id text PRIMARY KEY,
    name text NOT NULL,
    building text NOT NULL,
    position geography(Point, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS locations_position_gix
    ON public.locations USING gist (position);

-- En un volumen existente, devices.location_id ya contiene texto libre
-- ('AULA-204', 'LAB-101') sin tabla de referencia. Antes de exigir la FK,
-- sembramos un marcador geográfico neutro para cualquier location_id que un
-- dispositivo ya use y que todavía no tenga fila en locations. El seed
-- (01-iot.sql) sobrescribe estos marcadores con nombre, edificio y posición
-- reales al reaplicarse.
INSERT INTO public.locations (location_id, name, building, position)
SELECT DISTINCT
    device.location_id,
    device.location_id,
    device.location_id,
    ST_SetSRID(ST_MakePoint(-58.36820, -34.61778), 4326)::geography
FROM public.devices AS device
WHERE NOT EXISTS (
    SELECT 1
    FROM public.locations AS location
    WHERE location.location_id = device.location_id
);

DO $constraints$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.devices'::regclass
          AND conname = 'devices_location_id_fkey'
    ) THEN
        ALTER TABLE public.devices
            ADD CONSTRAINT devices_location_id_fkey
            FOREIGN KEY (location_id) REFERENCES public.locations (location_id);
    END IF;
END
$constraints$;

COMMIT;
