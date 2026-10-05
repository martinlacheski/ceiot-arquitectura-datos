\set ON_ERROR_STOP on

-- ST_DWithin opera sobre geography: el radio está expresado en metros.
-- Con 30 m desde AIR-002 se esperan exactamente AIR-002 (0 m) y
-- AMB-001 (aproximadamente 20 m); ACT-003 queda fuera, a unos 60 m.
WITH origin AS (
    SELECT position
    FROM devices
    WHERE device_id = 'AIR-002'
)
SELECT
    device.device_id,
    device.location_id,
    round(ST_Distance(device.position, origin.position)::numeric, 1) AS distance_m
FROM devices AS device
CROSS JOIN origin
WHERE ST_DWithin(device.position, origin.position, 30)
ORDER BY distance_m, device.device_id;

-- Resultado esperado: 1 índice GiST llamado devices_position_gix.
SELECT count(*) AS gist_position_index_count
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'devices'
  AND indexname = 'devices_position_gix'
  AND indexdef ILIKE '%USING gist%';

-- "¿Qué dispositivos se encuentran a menos de 2 km de esta ubicación?"
-- (filmina Clase 6). "Esta ubicación" es un punto arbitrario cercano al
-- Aula 204, no la posición exacta de ningún dispositivo. Resultado esperado:
-- AIR-002, AMB-001 (ENV-X) y ACT-003, los tres a menos de 100 m; AMB-005
-- (ENV-X en Ciudad Universitaria, a unos 10 km) queda excluido.
WITH origin AS (
    SELECT ST_SetSRID(ST_MakePoint(-58.36850, -34.61790), 4326)::geography AS position
)
SELECT
    device.device_id,
    device.model,
    location.name AS location_name,
    round(ST_Distance(device.position, origin.position)::numeric, 1) AS distance_m
FROM devices AS device
JOIN locations AS location ON location.location_id = device.location_id
CROSS JOIN origin
WHERE ST_DWithin(device.position, origin.position, 2000)
ORDER BY distance_m, device.device_id;

-- Resultado esperado: 1 índice GiST llamado locations_position_gix.
SELECT count(*) AS gist_locations_index_count
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'locations'
  AND indexname = 'locations_position_gix'
  AND indexdef ILIKE '%USING gist%';
