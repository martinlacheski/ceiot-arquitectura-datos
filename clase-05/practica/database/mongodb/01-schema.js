const databaseName = process.env.MONGO_DATABASE || process.env.MONGO_INITDB_DATABASE;
if (!/^[A-Za-z0-9_-]+$/.test(databaseName)) {
  throw new Error("MONGO_DATABASE must use only letters, numbers, underscores, or hyphens");
}

const lab = db.getSiblingDB(databaseName);
const validator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["device_id", "schema_version", "model", "location_id", "gateway_id", "configuration"],
    additionalProperties: false,
    properties: {
      _id: {},
      device_id: { bsonType: "string", pattern: "^[A-Z]+-[0-9]{3}$" },
      schema_version: { bsonType: "int", minimum: 1 },
      model: { enum: ["EnvMonitor-X", "AirQuality-Pro", "Ventilation-Actuator"] },
      location_id: { enum: ["AULA-204", "LAB-101"] },
      gateway_id: { enum: ["GW-AULA", "GW-LAB"] },
      configuration: {
        bsonType: "object",
        required: ["sample_interval_seconds", "variables"],
        properties: {
          sample_interval_seconds: { bsonType: "int", minimum: 1 },
          variables: { bsonType: "array", minItems: 1, uniqueItems: true, items: { bsonType: "string" } },
          calibration: { bsonType: "object" },
          alerts: { bsonType: "object" },
          control: { bsonType: "object" }
        }
      }
    }
  }
};

if (lab.getCollectionInfos({ name: "devices" }).length === 0) {
  lab.createCollection("devices", { validator, validationLevel: "strict", validationAction: "error" });
} else {
  lab.runCommand({ collMod: "devices", validator, validationLevel: "strict", validationAction: "error" });
}

lab.devices.createIndex({ device_id: 1 }, { name: "uq_device_id", unique: true });
lab.devices.createIndex({ location_id: 1, gateway_id: 1 }, { name: "ix_location_gateway" });
lab.devices.createIndex({ model: 1 }, { name: "ix_model" });
