// CONTEXTO: P4 recorre conectividad y dependencias desde GW-LAB.
// EJEMPLO EJECUTABLE: encuentra AIR-002 y el actuador que depende de sus lecturas.
// OBSERVACIÓN ESPERADA: informa 8 nodos, 8 relaciones, AIR-002 y ACT-003 afectados.
// VARIACIONES SEGURAS: cambiar GW-LAB por GW-AULA y comparar el alcance.
// RECUPERACIÓN: estas lecturas no modifican el grafo; pueden repetirse sin cambios.

MATCH (node)
WITH count(node) AS nodes
MATCH ()-[relationship]->()
RETURN nodes, count(relationship) AS relationships;

MATCH (:Gateway {id: "GW-LAB"})-[:CONNECTS]->(source:Device)
OPTIONAL MATCH (affected:Device)-[:DEPENDS_ON*1..]->(source)
WITH collect(source) + collect(affected) AS devices
UNWIND devices AS device
WITH DISTINCT device
WHERE device IS NOT NULL
RETURN device.id AS affected
ORDER BY affected;
