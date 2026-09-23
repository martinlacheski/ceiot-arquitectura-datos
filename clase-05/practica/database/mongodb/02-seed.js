const databaseName = process.env.MONGO_DATABASE || process.env.MONGO_INITDB_DATABASE;
if (!/^[A-Za-z0-9_-]+$/.test(databaseName)) {
  throw new Error("MONGO_DATABASE must use only letters, numbers, underscores, or hyphens");
}

const devices = db.getSiblingDB(databaseName).devices;
const canonical = [
  {
    device_id: "AMB-001",
    schema_version: NumberInt(1),
    model: "EnvMonitor-X",
    location_id: "AULA-204",
    gateway_id: "GW-AULA",
    configuration: {
      sample_interval_seconds: NumberInt(60),
      variables: ["temperature", "humidity"]
    }
  },
  {
    device_id: "AIR-002",
    schema_version: NumberInt(2),
    model: "AirQuality-Pro",
    location_id: "LAB-101",
    gateway_id: "GW-LAB",
    configuration: {
      sample_interval_seconds: NumberInt(30),
      variables: ["temperature", "humidity", "co2"],
      calibration: { co2_offset_ppm: NumberInt(12) },
      alerts: { co2_max_ppm: NumberInt(1000) }
    }
  },
  {
    device_id: "ACT-003",
    schema_version: NumberInt(1),
    model: "Ventilation-Actuator",
    location_id: "AULA-204",
    gateway_id: "GW-AULA",
    configuration: {
      sample_interval_seconds: NumberInt(30),
      variables: ["ventilation_state"],
      control: { depends_on: "AIR-002", co2_trigger_ppm: NumberInt(1000) }
    }
  }
];

for (const document of canonical) {
  devices.replaceOne({ device_id: document.device_id }, document, { upsert: true });
}
devices.deleteMany({ device_id: { $nin: canonical.map((item) => item.device_id) } });

const count = devices.countDocuments({});
if (count !== canonical.length) {
  throw new Error(`Expected ${canonical.length} canonical devices, found ${count}`);
}
