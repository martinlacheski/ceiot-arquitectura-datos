\set ON_ERROR_STOP on

BEGIN;

INSERT INTO locations (
    location_id,
    name,
    building,
    position
)
VALUES
    (
        'AULA-204',
        'Aula 204',
        'Edificio Principal',
        ST_SetSRID(ST_MakePoint(-58.36820, -34.61778), 4326)::geography
    ),
    (
        'LAB-101',
        'Laboratorio 101',
        'Edificio Principal',
        ST_SetSRID(ST_MakePoint(-58.36820, -34.61760), 4326)::geography
    ),
    (
        'CIUDAD-UNIV',
        'Ciudad Universitaria',
        'Predio CUI',
        ST_SetSRID(ST_MakePoint(-58.44350, -34.54200), 4326)::geography
    )
ON CONFLICT (location_id) DO UPDATE
SET name = EXCLUDED.name,
    building = EXCLUDED.building,
    position = EXCLUDED.position;

INSERT INTO devices (
    device_id,
    model,
    location_id,
    position,
    depends_on_device_id
)
VALUES
    (
        'AIR-002',
        'AirQuality-Pro',
        'LAB-101',
        ST_SetSRID(ST_MakePoint(-58.36820, -34.61760), 4326)::geography,
        NULL
    ),
    (
        'AMB-001',
        'ENV-X',
        'AULA-204',
        ST_SetSRID(ST_MakePoint(-58.36820, -34.61778), 4326)::geography,
        NULL
    ),
    (
        'ACT-003',
        'Ventilation-Actuator',
        'AULA-204',
        ST_SetSRID(ST_MakePoint(-58.36820, -34.61814), 4326)::geography,
        'AIR-002'
    ),
    (
        'AMB-005',
        'ENV-X',
        'CIUDAD-UNIV',
        ST_SetSRID(ST_MakePoint(-58.44350, -34.54200), 4326)::geography,
        NULL
    )
ON CONFLICT (device_id) DO UPDATE
SET model = EXCLUDED.model,
    location_id = EXCLUDED.location_id,
    position = EXCLUDED.position,
    depends_on_device_id = EXCLUDED.depends_on_device_id;

-- Ocho mediciones fijas del 2025-05-12: los ejemplos temporales fijos y
-- algunos tests siguen apoyándose en este día exacto.
INSERT INTO measurements (
    device_id,
    measured_at,
    variable,
    value,
    unit,
    quality
)
VALUES
    ('AIR-002', '2025-05-12T10:32:00Z', 'co2', 812, 'ppm', 'GOOD'),
    ('AIR-002', '2025-05-12T10:32:00Z', 'temperature', 24.6, 'C', 'GOOD'),
    ('AIR-002', '2025-05-12T10:31:30Z', 'co2', 806, 'ppm', 'GOOD'),
    ('AIR-002', '2025-05-12T10:31:30Z', 'humidity', 47.8, 'percent', 'GOOD'),
    ('AIR-002', '2025-05-12T10:31:00Z', 'co2', 799, 'ppm', 'GOOD'),
    ('AMB-001', '2025-05-12T10:32:00Z', 'temperature', 24.6, 'C', 'GOOD'),
    ('AMB-001', '2025-05-12T10:32:00Z', 'humidity', 48.2, 'percent', 'GOOD'),
    ('ACT-003', '2025-05-12T10:32:00Z', 'ventilation_state', 0, 'boolean', 'GOOD')
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
INSERT INTO measurements (device_id, measured_at, variable, value, unit, quality)
SELECT
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

INSERT INTO measurements (device_id, measured_at, variable, value, unit, quality)
SELECT
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

INSERT INTO manual_documents (
    document_id,
    version,
    title,
    object_key,
    content_type,
    storage_status
)
VALUES (
    'env-x-manual',
    1,
    'Manual de calibración ENV-X',
    'manuales/env-x/v1/manual_ENV_X.pdf',
    'application/pdf',
    'pending_upload'
)
ON CONFLICT (document_id, version) DO UPDATE
SET title = EXCLUDED.title,
    object_key = EXCLUDED.object_key,
    content_type = EXCLUDED.content_type,
    storage_status = CASE
        -- Una repetición no debe desmentir una carga ya verificada para la
        -- misma versión y clave. Si cambia la clave, vuelve a quedar pendiente.
        WHEN manual_documents.storage_status = 'available'
         AND manual_documents.object_key = EXCLUDED.object_key
         AND manual_documents.content_type = EXCLUDED.content_type
        THEN 'available'
        ELSE 'pending_upload'
    END;

COMMIT;

-- Estadísticas frescas para que el esquema de Text-to-SQL vea los valores cargados.
ANALYZE locations, devices, measurements, manual_documents;

-- En un volumen fresco, antes de cargar otros PDF: 3 ubicaciones,
-- 4 dispositivos, 1 registro de manual y 8 + 96 = 104 mediciones (8 fijas del
-- 2025-05-12 más 48 horas de temperatura y 48 de humedad de ENV-X ancladas a
-- la hora de ejecución). Repetir el seed en una hora distinta agrega mediciones
-- nuevas en vez de reemplazar las anteriores: el recuento horario crece con
-- cada resiembra tardía y no vuelve a 104. El estado del manual queda pendiente
-- hasta que el loader verifica S3, pero una carga ya verificada no se degrada
-- al resembrar.
SELECT
    (SELECT count(*) FROM locations) AS location_count,
    (SELECT count(*) FROM devices) AS device_count,
    (SELECT count(*) FROM measurements) AS measurement_count,
    (SELECT count(*) FROM manual_documents) AS manual_count;
