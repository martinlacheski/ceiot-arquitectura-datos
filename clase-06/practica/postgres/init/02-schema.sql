\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS locations (
    location_id text PRIMARY KEY,
    name text NOT NULL,
    building text NOT NULL,
    position geography(Point, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS locations_position_gix
    ON locations USING gist (position);

CREATE TABLE IF NOT EXISTS devices (
    device_id text PRIMARY KEY,
    model text NOT NULL,
    location_id text NOT NULL REFERENCES locations (location_id),
    position geography(Point, 4326) NOT NULL,
    depends_on_device_id text REFERENCES devices (device_id)
);

CREATE INDEX IF NOT EXISTS devices_position_gix
    ON devices USING gist (position);

CREATE TABLE IF NOT EXISTS measurements (
    device_id text NOT NULL REFERENCES devices (device_id),
    measured_at timestamptz NOT NULL,
    variable text NOT NULL,
    value numeric(12, 3) NOT NULL,
    unit text NOT NULL,
    quality text NOT NULL CHECK (quality IN ('GOOD', 'SUSPECT', 'BAD')),
    PRIMARY KEY (device_id, measured_at, variable)
);

SELECT create_hypertable(
    'measurements',
    by_range('measured_at'),
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS measurements_device_time_idx
    ON measurements (device_id, measured_at DESC);

CREATE TABLE IF NOT EXISTS manual_documents (
    document_id text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    title text NOT NULL,
    object_key text NOT NULL UNIQUE,
    content_type text NOT NULL,
    storage_status text NOT NULL CHECK (storage_status IN ('pending_upload', 'available')),
    PRIMARY KEY (document_id, version)
);
