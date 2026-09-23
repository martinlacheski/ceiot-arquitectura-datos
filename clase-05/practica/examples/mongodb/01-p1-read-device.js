// CONTEXTO: P1 recupera la configuración completa de AIR-002 por device_id.
// EJEMPLO EJECUTABLE: consulta el agregado documental y cuenta el estado canónico.
// OBSERVACIÓN ESPERADA: imprime count=3 y el único documento de AIR-002.
// VARIACIONES SEGURAS: cambiar solo el device_id por AMB-001 o ACT-003.
// RECUPERACIÓN: esta lectura no modifica datos; puede repetirse sin cambios.

const devices = db.getSiblingDB(process.env.MONGO_INITDB_DATABASE).devices;
print(`count=${devices.countDocuments({})}`);
printjson(devices.findOne({ device_id: "AIR-002" }, { _id: 0 }));
