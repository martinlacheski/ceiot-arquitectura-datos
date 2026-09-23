CREATE CONSTRAINT organization_id IF NOT EXISTS
FOR (node:Organization) REQUIRE node.id IS UNIQUE;
CREATE CONSTRAINT location_id IF NOT EXISTS
FOR (node:Location) REQUIRE node.id IS UNIQUE;
CREATE CONSTRAINT gateway_id IF NOT EXISTS
FOR (node:Gateway) REQUIRE node.id IS UNIQUE;
CREATE CONSTRAINT device_id IF NOT EXISTS
FOR (node:Device) REQUIRE node.id IS UNIQUE;
CREATE INDEX device_model IF NOT EXISTS
FOR (node:Device) ON (node.model);
CREATE INDEX location_name IF NOT EXISTS
FOR (node:Location) ON (node.name);
