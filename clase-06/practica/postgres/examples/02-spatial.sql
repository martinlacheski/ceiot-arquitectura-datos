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
