// CONTEXTO: un camino alternativo cambia conectividad sin borrar la dependencia.
// EJEMPLO EJECUTABLE: agrega un enlace de respaldo desde GW-AULA hacia AIR-002.
// OBSERVACIÓN ESPERADA: AIR-002 tiene dos gateways, pero ACT-003 aún depende de él.
// VARIACIONES SEGURAS: repetir MERGE no duplica la relación BACKUP_CONNECTS.
// RECUPERACIÓN: ejecutar 03-p4-recover.cypher para eliminar solo el enlace de respaldo.

MATCH (gateway:Gateway {id: "GW-AULA"}), (device:Device {id: "AIR-002"})
MERGE (gateway)-[:BACKUP_CONNECTS]->(device);

MATCH (gateway:Gateway)-[:CONNECTS|BACKUP_CONNECTS]->(device:Device {id: "AIR-002"})
RETURN gateway.id AS gateway
ORDER BY gateway;
