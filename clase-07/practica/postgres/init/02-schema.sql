\set ON_ERROR_STOP on

-- Multi-tenant sobre tablas compartidas: cada organización es un tenant y
-- todas las tablas de telemetría llevan organization_id (desnormalizado a
-- propósito: así una política RLS puede filtrar cada tabla sin hacer JOIN).
CREATE TABLE IF NOT EXISTS organizations (
    organization_id bigint PRIMARY KEY,
    name text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS locations (
    location_id text PRIMARY KEY,
    organization_id bigint NOT NULL REFERENCES organizations (organization_id),
    name text NOT NULL,
    building text NOT NULL,
    position geography(Point, 4326) NOT NULL,
    -- Clave objetivo de las claves foráneas compuestas de devices.
    UNIQUE (organization_id, location_id)
);

CREATE INDEX IF NOT EXISTS locations_position_gix
    ON locations USING gist (position);

CREATE TABLE IF NOT EXISTS devices (
    device_id text PRIMARY KEY,
    organization_id bigint NOT NULL REFERENCES organizations (organization_id),
    model text NOT NULL,
    location_id text NOT NULL,
    position geography(Point, 4326) NOT NULL,
    depends_on_device_id text,
    sampling_interval_seconds integer NOT NULL DEFAULT 60
        CHECK (sampling_interval_seconds > 0),
    -- Integridad entre tenants: un equipo sólo puede estar en una ubicación
    -- de su propia organización y depender de un equipo de su organización.
    FOREIGN KEY (organization_id, location_id)
        REFERENCES locations (organization_id, location_id),
    UNIQUE (organization_id, device_id),
    FOREIGN KEY (organization_id, depends_on_device_id)
        REFERENCES devices (organization_id, device_id)
);

CREATE INDEX IF NOT EXISTS devices_position_gix
    ON devices USING gist (position);

CREATE INDEX IF NOT EXISTS devices_organization_idx
    ON devices (organization_id, location_id);

CREATE TABLE IF NOT EXISTS measurements (
    organization_id bigint NOT NULL REFERENCES organizations (organization_id),
    device_id text NOT NULL,
    measured_at timestamptz NOT NULL,
    variable text NOT NULL,
    value numeric(12, 3) NOT NULL,
    unit text NOT NULL,
    quality text NOT NULL CHECK (quality IN ('GOOD', 'SUSPECT', 'BAD')),
    PRIMARY KEY (device_id, measured_at, variable),
    -- Una medición no puede apuntar al equipo de otra organización.
    FOREIGN KEY (organization_id, device_id)
        REFERENCES devices (organization_id, device_id)
);

SELECT create_hypertable(
    'measurements',
    by_range('measured_at'),
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS measurements_device_time_idx
    ON measurements (device_id, measured_at DESC);

CREATE INDEX IF NOT EXISTS measurements_org_device_time_idx
    ON measurements (organization_id, device_id, measured_at DESC);

CREATE TABLE IF NOT EXISTS manual_documents (
    document_id text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    title text NOT NULL,
    object_key text NOT NULL UNIQUE,
    content_type text NOT NULL,
    storage_status text NOT NULL CHECK (storage_status IN ('pending_upload', 'available')),
    PRIMARY KEY (document_id, version)
);
