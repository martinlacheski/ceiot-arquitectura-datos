\set ON_ERROR_STOP on

BEGIN;

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
        'EnvMonitor-X',
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
    )
ON CONFLICT (device_id) DO UPDATE
SET model = EXCLUDED.model,
    location_id = EXCLUDED.location_id,
    position = EXCLUDED.position,
    depends_on_device_id = EXCLUDED.depends_on_device_id;

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

INSERT INTO manual_documents (
    document_id,
    version,
    title,
    object_key,
    content_type,
    storage_status
)
VALUES (
    'air-quality-pro-manual',
    1,
    'Manual de calibración AirQuality-Pro',
    'manuales/air-quality-pro/v1/manual.pdf',
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

-- En un volumen fresco, antes de cargar otros PDF: 3 dispositivos,
-- 8 mediciones y 1 registro de manual. Después de cargas, manual_count crece:
-- repetir el seed conserva esos uploads, no los elimina. El estado del manual
-- queda pendiente hasta que el loader verifica S3, pero una carga ya verificada
-- no se degrada al resembrar.
SELECT
    (SELECT count(*) FROM devices) AS device_count,
    (SELECT count(*) FROM measurements) AS measurement_count,
    (SELECT count(*) FROM manual_documents) AS manual_count;
