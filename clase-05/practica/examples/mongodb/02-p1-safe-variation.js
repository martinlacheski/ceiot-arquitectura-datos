// CONTEXTO: P1 admite evolución versionada de una configuración embebida.
// EJEMPLO EJECUTABLE: agrega firmware_auto_update solo a AIR-002.
// OBSERVACIÓN ESPERADA: AIR-002 queda en schema_version=3 sin modificar otros documentos.
// VARIACIONES SEGURAS: cambiar únicamente el valor booleano de firmware_auto_update.
// RECUPERACIÓN: ejecutar 03-p1-recover.js para restaurar la semilla canónica.

const devices = db.getSiblingDB(process.env.MONGO_INITDB_DATABASE).devices;
devices.updateOne(
  { device_id: "AIR-002" },
  {
    $set: {
      schema_version: NumberInt(3),
      "configuration.firmware_auto_update": true
    }
  }
);
printjson(
  devices.findOne(
    { device_id: "AIR-002" },
    { _id: 0, schema_version: 1, "configuration.firmware_auto_update": 1 }
  )
);
