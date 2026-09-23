MERGE (organization:Organization {id: 'ORG-FIUBA'})
SET organization.name = 'Facultad de Ingeniería'
MERGE (classroom:Location {id: 'AULA-204'})
SET classroom.name = 'Aula 204'
MERGE (laboratory:Location {id: 'LAB-101'})
SET laboratory.name = 'Laboratorio 101'
MERGE (classroomGateway:Gateway {id: 'GW-AULA'})
SET classroomGateway.name = 'Gateway del aula'
MERGE (laboratoryGateway:Gateway {id: 'GW-LAB'})
SET laboratoryGateway.name = 'Gateway del laboratorio'
MERGE (ambient:Device {id: 'AMB-001'})
SET ambient.model = 'EnvMonitor-X'
MERGE (air:Device {id: 'AIR-002'})
SET air.model = 'AirQuality-Pro'
MERGE (actuator:Device {id: 'ACT-003'})
SET actuator.model = 'Ventilation-Actuator'
MERGE (organization)-[:HAS_LOCATION]->(classroom)
MERGE (organization)-[:HAS_LOCATION]->(laboratory)
MERGE (classroom)-[:HAS_GATEWAY]->(classroomGateway)
MERGE (laboratory)-[:HAS_GATEWAY]->(laboratoryGateway)
MERGE (classroomGateway)-[:CONNECTS]->(ambient)
MERGE (classroomGateway)-[:CONNECTS]->(actuator)
MERGE (laboratoryGateway)-[:CONNECTS]->(air)
MERGE (actuator)-[dependency:DEPENDS_ON]->(air)
SET dependency.reason = 'ventilation_control';
