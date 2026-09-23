// CONTEXTO: restaura la topología canónica sin tocar nodos ni relaciones base.
// EJEMPLO EJECUTABLE: elimina solo el enlace BACKUP_CONNECTS de la variación.
// OBSERVACIÓN ESPERADA: el grafo vuelve explícitamente a 8 nodos y 8 relaciones.
// VARIACIONES SEGURAS: repetir la consulta cuando no existe el enlace conserva 8/8.
// RECUPERACIÓN: la propia operación es idempotente y confirma el estado canónico.

MATCH (:Gateway {id: "GW-AULA"})-[backup:BACKUP_CONNECTS]->(:Device {id: "AIR-002"})
DELETE backup;

MATCH (node)
WITH count(node) AS nodes
MATCH ()-[relationship]->()
RETURN nodes, count(relationship) AS relationships;
