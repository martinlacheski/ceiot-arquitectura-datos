CREATE KEYSPACE IF NOT EXISTS __KEYSPACE__
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': __REPLICATION_FACTOR__
};

CREATE TABLE IF NOT EXISTS __KEYSPACE__.measurement_by_device_day (
  device_id text,
  day date,
  measured_at timestamp,
  variable text,
  value double,
  unit text,
  quality text,
  PRIMARY KEY ((device_id, day), measured_at, variable)
) WITH CLUSTERING ORDER BY (measured_at DESC, variable ASC)
  AND comment = 'P3: bounded daily time ranges per device';
