// CONTEXTO: restaura los tres agregados canónicos después de una variación.
// EJEMPLO EJECUTABLE: carga la semilla idempotente usada por el laboratorio.
// OBSERVACIÓN ESPERADA: imprime count=3 y AIR-002 con schema_version=2.
// VARIACIONES SEGURAS: repetir la recuperación conserva el mismo estado canónico.
// RECUPERACIÓN: la propia operación es idempotente y puede repetirse.

load("/lab/database/02-seed.js");

const recoveredDevices = db.getSiblingDB(process.env.MONGO_INITDB_DATABASE).devices;
print(`count=${recoveredDevices.countDocuments({})}`);
printjson(
  recoveredDevices.findOne(
    { device_id: "AIR-002" },
    { _id: 0, device_id: 1, schema_version: 1 }
  )
);
