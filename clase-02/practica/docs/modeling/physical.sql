CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(120) NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(320) NOT NULL UNIQUE,
  display_name VARCHAR(120) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE organization_users (
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role VARCHAR(40) NOT NULL DEFAULT 'viewer' CHECK (role IN ('owner', 'operator', 'viewer')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, user_id)
);
CREATE TABLE locations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  name VARCHAR(120) NOT NULL,
  description TEXT,
  latitude NUMERIC(8,5) CHECK (latitude BETWEEN -90 AND 90),
  longitude NUMERIC(8,5) CHECK (longitude BETWEEN -180 AND 180),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (organization_id, name)
);
CREATE TABLE devices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  name VARCHAR(120) NOT NULL,
  serial_number VARCHAR(120) NOT NULL UNIQUE,
  model VARCHAR(120),
  installed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE measurements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id UUID NOT NULL REFERENCES devices(id) ON DELETE RESTRICT,
  variable VARCHAR(80) NOT NULL,
  value NUMERIC(14,4) NOT NULL,
  unit VARCHAR(24) NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (variable <> ''), CHECK (unit <> '')
);
CREATE TABLE device_status_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id UUID NOT NULL REFERENCES devices(id) ON DELETE RESTRICT,
  status VARCHAR(30) NOT NULL CHECK (status IN ('active', 'inactive', 'maintenance')),
  started_at TIMESTAMPTZ NOT NULL,
  ended_at TIMESTAMPTZ,
  CHECK (ended_at IS NULL OR ended_at > started_at)
);
CREATE TABLE device_location_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id UUID NOT NULL REFERENCES devices(id) ON DELETE RESTRICT,
  location_id UUID NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
  started_at TIMESTAMPTZ NOT NULL,
  ended_at TIMESTAMPTZ,
  CHECK (ended_at IS NULL OR ended_at > started_at)
);
CREATE INDEX measurements_device_recorded_at_idx ON measurements (device_id, recorded_at DESC);
CREATE INDEX devices_organization_id_idx ON devices (organization_id);
CREATE INDEX locations_organization_id_idx ON locations (organization_id);
CREATE UNIQUE INDEX device_status_one_current_idx ON device_status_history (device_id) WHERE ended_at IS NULL;
CREATE UNIQUE INDEX device_location_one_current_idx ON device_location_history (device_id) WHERE ended_at IS NULL;

COMMENT ON COLUMN devices.organization_id IS 'Ownership/scoping only in Clase 2; it is not authentication or tenant security.';
