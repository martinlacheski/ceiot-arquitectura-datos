\set ON_ERROR_STOP on

BEGIN;

-- Dos organizaciones (tenants) que comparten las mismas tablas. La
-- Organización A conserva los datos de la clase 6; la B tiene los suyos.
INSERT INTO organizations (organization_id, name)
VALUES
    (1, 'Organización A — Facultad'),
    (2, 'Organización B — Planta')
ON CONFLICT (organization_id) DO UPDATE
SET name = EXCLUDED.name;

INSERT INTO locations (
    organization_id,
    location_id,
    name,
    building,
    position
)
VALUES
    (
        1,
        'AULA-204',
        'Aula 204',
        'Edificio Principal',
        ST_SetSRID(ST_MakePoint(-58.36820, -34.61778), 4326)::geography
    ),
    (
        1,
        'LAB-101',
        'Laboratorio 101',
        'Edificio Principal',
        ST_SetSRID(ST_MakePoint(-58.36820, -34.61760), 4326)::geography
    ),
    (
        1,
        'CIUDAD-UNIV',
        'Ciudad Universitaria',
        'Predio CUI',
        ST_SetSRID(ST_MakePoint(-58.44350, -34.54200), 4326)::geography
    ),
    (
        2,
        'PLANTA-01',
        'Planta 1 - Línea de ensamblado',
        'Planta Industrial Norte',
        ST_SetSRID(ST_MakePoint(-58.52900, -34.46800), 4326)::geography
    )
ON CONFLICT (location_id) DO UPDATE
SET organization_id = EXCLUDED.organization_id,
    name = EXCLUDED.name,
    building = EXCLUDED.building,
    position = EXCLUDED.position;

INSERT INTO devices (
    organization_id,
    device_id,
    model,
    location_id,
    position,
    depends_on_device_id
)
VALUES
    (
        1,
        'AIR-002',
        'AirQuality-Pro',
        'LAB-101',
        ST_SetSRID(ST_MakePoint(-58.36820, -34.61760), 4326)::geography,
        NULL
    ),
    (
        1,
        'AMB-001',
        'ENV-X',
        'AULA-204',
        ST_SetSRID(ST_MakePoint(-58.36820, -34.61778), 4326)::geography,
        NULL
    ),
    (
        1,
        'ACT-003',
        'Ventilation-Actuator',
        'AULA-204',
        ST_SetSRID(ST_MakePoint(-58.36820, -34.61814), 4326)::geography,
        'AIR-002'
    ),
    (
        1,
        'AMB-005',
        'ENV-X',
        'CIUDAD-UNIV',
        ST_SetSRID(ST_MakePoint(-58.44350, -34.54200), 4326)::geography,
        NULL
    ),
    (
        2,
        'PLT-001',
        'ENV-X',
        'PLANTA-01',
        ST_SetSRID(ST_MakePoint(-58.52900, -34.46800), 4326)::geography,
        NULL
    ),
    (
        2,
        'PLT-002',
        'AirQuality-Pro',
        'PLANTA-01',
        ST_SetSRID(ST_MakePoint(-58.52910, -34.46810), 4326)::geography,
        NULL
    )
ON CONFLICT (device_id) DO UPDATE
SET organization_id = EXCLUDED.organization_id,
    model = EXCLUDED.model,
    location_id = EXCLUDED.location_id,
    position = EXCLUDED.position,
    depends_on_device_id = EXCLUDED.depends_on_device_id;

-- Ocho mediciones fijas del 2025-05-12: los ejemplos temporales fijos y
-- algunos tests siguen apoyándose en este día exacto.
INSERT INTO measurements (
    organization_id,
    device_id,
    measured_at,
    variable,
    value,
    unit,
    quality
)
VALUES
    (1, 'AIR-002', '2025-05-12T10:32:00Z', 'co2', 812, 'ppm', 'GOOD'),
    (1, 'AIR-002', '2025-05-12T10:32:00Z', 'temperature', 24.6, 'C', 'GOOD'),
    (1, 'AIR-002', '2025-05-12T10:31:30Z', 'co2', 806, 'ppm', 'GOOD'),
    (1, 'AIR-002', '2025-05-12T10:31:30Z', 'humidity', 47.8, 'percent', 'GOOD'),
    (1, 'AIR-002', '2025-05-12T10:31:00Z', 'co2', 799, 'ppm', 'GOOD'),
    (1, 'AMB-001', '2025-05-12T10:32:00Z', 'temperature', 24.6, 'C', 'GOOD'),
    (1, 'AMB-001', '2025-05-12T10:32:00Z', 'humidity', 48.2, 'percent', 'GOOD'),
    (1, 'ACT-003', '2025-05-12T10:32:00Z', 'ventilation_state', 0, 'boolean', 'GOOD')
ON CONFLICT (device_id, measured_at, variable) DO UPDATE
SET value = EXCLUDED.value,
    unit = EXCLUDED.unit,
    quality = EXCLUDED.quality;

-- Historial horario reciente de ENV-X (AMB-001) en el Aula 204, anclado a
-- date_trunc('hour', now()), para que "últimas 24 horas" siempre tenga datos.
-- Los valores son deterministas (sin random()); las últimas ~6 horas quedan
-- marcadas SUSPECT con un salto de temperatura para simular una anomalía.
-- Repetir el seed en una hora distinta agrega filas nuevas (measured_at
-- cambia): el recuento total de mediciones crece con cada resiembra tardía,
-- no se mantiene fijo como en el rango histórico del 2025-05-12.
INSERT INTO measurements (organization_id, device_id, measured_at, variable, value, unit, quality)
SELECT
    1,
    'AMB-001',
    date_trunc('hour', now()) - (offset_hours || ' hours')::interval,
    'temperature',
    round(
        (23.0 + (offset_hours % 5) * 0.4)
        + CASE WHEN offset_hours < 6 THEN 8.0 ELSE 0.0 END,
        1
    ),
    'C',
    CASE WHEN offset_hours < 6 THEN 'SUSPECT' ELSE 'GOOD' END
FROM generate_series(0, 47) AS offset_hours
ON CONFLICT (device_id, measured_at, variable) DO UPDATE
SET value = EXCLUDED.value,
    unit = EXCLUDED.unit,
    quality = EXCLUDED.quality;

INSERT INTO measurements (organization_id, device_id, measured_at, variable, value, unit, quality)
SELECT
    1,
    'AMB-001',
    date_trunc('hour', now()) - (offset_hours || ' hours')::interval,
    'humidity',
    round(45.0 + (offset_hours % 8) * 0.5, 1),
    'percent',
    'GOOD'
FROM generate_series(0, 47) AS offset_hours
ON CONFLICT (device_id, measured_at, variable) DO UPDATE
SET value = EXCLUDED.value,
    unit = EXCLUDED.unit,
    quality = EXCLUDED.quality;

-- Organización B: dos equipos de la planta con 48 horas de historial horario
-- de las mismas variables, para que las preguntas entre organizaciones tengan
-- sentido. PLT-001 (ENV-X) mide temperatura y humedad; PLT-002 (AirQuality-Pro)
-- mide CO2. Los valores son deterministas y se anclan a la hora de ejecución.
INSERT INTO measurements (organization_id, device_id, measured_at, variable, value, unit, quality)
SELECT
    2,
    'PLT-001',
    date_trunc('hour', now()) - (offset_hours || ' hours')::interval,
    'temperature',
    round(28.0 + (offset_hours % 6) * 0.5, 1),
    'C',
    'GOOD'
FROM generate_series(0, 47) AS offset_hours
ON CONFLICT (device_id, measured_at, variable) DO UPDATE
SET value = EXCLUDED.value,
    unit = EXCLUDED.unit,
    quality = EXCLUDED.quality;

INSERT INTO measurements (organization_id, device_id, measured_at, variable, value, unit, quality)
SELECT
    2,
    'PLT-001',
    date_trunc('hour', now()) - (offset_hours || ' hours')::interval,
    'humidity',
    round(38.0 + (offset_hours % 7) * 0.6, 1),
    'percent',
    'GOOD'
FROM generate_series(0, 47) AS offset_hours
ON CONFLICT (device_id, measured_at, variable) DO UPDATE
SET value = EXCLUDED.value,
    unit = EXCLUDED.unit,
    quality = EXCLUDED.quality;

INSERT INTO measurements (organization_id, device_id, measured_at, variable, value, unit, quality)
SELECT
    2,
    'PLT-002',
    date_trunc('hour', now()) - (offset_hours || ' hours')::interval,
    'co2',
    900 + (offset_hours % 9) * 25,
    'ppm',
    CASE WHEN offset_hours % 12 = 0 THEN 'SUSPECT' ELSE 'GOOD' END
FROM generate_series(0, 47) AS offset_hours
ON CONFLICT (device_id, measured_at, variable) DO UPDATE
SET value = EXCLUDED.value,
    unit = EXCLUDED.unit,
    quality = EXCLUDED.quality;

COMMIT;

-- Estadísticas frescas para que el esquema de Text-to-SQL vea los valores cargados.
ANALYZE organizations, locations, devices, measurements;

-- En un volumen fresco: 2 organizaciones. La A tiene 3 ubicaciones, 4
-- dispositivos y 8 + 96 = 104 mediciones (8 fijas del 2025-05-12 más 48 horas
-- de temperatura y 48 de humedad de ENV-X ancladas a la hora de ejecución). La
-- B tiene 1 ubicación, 2 dispositivos y 48 x 3 = 144 mediciones. Repetir el
-- seed en una hora distinta agrega mediciones nuevas en vez de reemplazar las
-- anteriores: el recuento horario crece con cada resiembra tardía.
SELECT count(*) AS organization_count FROM organizations;

SELECT
    organization.organization_id,
    organization.name,
    (SELECT count(*) FROM locations AS item
      WHERE item.organization_id = organization.organization_id) AS location_count,
    (SELECT count(*) FROM devices AS item
      WHERE item.organization_id = organization.organization_id) AS device_count,
    (SELECT count(*) FROM measurements AS item
      WHERE item.organization_id = organization.organization_id) AS measurement_count
FROM organizations AS organization
ORDER BY organization.organization_id;
