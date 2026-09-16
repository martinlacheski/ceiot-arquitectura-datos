-- Seed determinista e idempotente de registro_ambiental.
-- 2 organizaciones x 2 ubicaciones cada una x 5 dispositivos x 4 lecturas = 20 filas.
-- Al aplicar el desdoblamiento de 1FN (sql/02-normalizacion.sql) estas 20 filas
-- producen exactamente 50 mediciones individuales (detalle por dispositivo más
-- abajo y en el README). Los valores de variables/valores son paralelos por
-- posición: el primer valor de "valores" corresponde a la primera variable, etc.

INSERT INTO registro_ambiental
    (id, dispositivo_id, dispositivo_nombre, numero_serie, variables, valores,
     ubicacion_id, ubicacion_nombre, organizacion_id, organizacion_nombre, registrado_en)
VALUES
-- Dispositivo 15 "Ambiente 01" (Aula 204, FIUBA) -> 2+3+2+3 = 10 mediciones
(1,  15, 'Ambiente 01', 'AMB-15-01', 'temperatura,humedad',        '22.5,55',        4, 'Aula 204', 1, 'FIUBA', '2026-03-02 10:30:00'),
(2,  15, 'Ambiente 01', 'AMB-15-01', 'temperatura,humedad,co2',    '22.8,54,620',    4, 'Aula 204', 1, 'FIUBA', '2026-03-03 10:30:00'),
(3,  15, 'Ambiente 01', 'AMB-15-01', 'temperatura,humedad',        '23.0,53',        4, 'Aula 204', 1, 'FIUBA', '2026-03-04 10:30:00'),
(4,  15, 'Ambiente 01', 'AMB-15-01', 'temperatura,humedad,co2',    '23.4,52,640',    4, 'Aula 204', 1, 'FIUBA', '2026-03-05 10:30:00'),

-- Dispositivo 16 "Ambiente 02" (Aula 204, FIUBA) -> 2+2+2+2 = 8 mediciones
(5,  16, 'Ambiente 02', 'AMB-16-01', 'temperatura,humedad',        '21.9,58',        4, 'Aula 204', 1, 'FIUBA', '2026-03-02 11:00:00'),
(6,  16, 'Ambiente 02', 'AMB-16-01', 'temperatura,humedad',        '22.1,57',        4, 'Aula 204', 1, 'FIUBA', '2026-03-03 11:00:00'),
(7,  16, 'Ambiente 02', 'AMB-16-01', 'temperatura,humedad',        '22.4,56',        4, 'Aula 204', 1, 'FIUBA', '2026-03-04 11:00:00'),
(8,  16, 'Ambiente 02', 'AMB-16-01', 'temperatura,humedad',        '22.6,55',        4, 'Aula 204', 1, 'FIUBA', '2026-03-05 11:00:00'),

-- Dispositivo 17 "Ambiente 03" (Laboratorio 101, FIUBA) -> 3+3+3+3 = 12 mediciones
(9,  17, 'Ambiente 03', 'AMB-17-01', 'temperatura,humedad,co2',    '20.5,48,510',    5, 'Laboratorio 101', 1, 'FIUBA', '2026-03-02 09:15:00'),
(10, 17, 'Ambiente 03', 'AMB-17-01', 'temperatura,humedad,co2',    '20.8,47,505',    5, 'Laboratorio 101', 1, 'FIUBA', '2026-03-03 09:15:00'),
(11, 17, 'Ambiente 03', 'AMB-17-01', 'temperatura,humedad,co2',    '21.0,46,515',    5, 'Laboratorio 101', 1, 'FIUBA', '2026-03-04 09:15:00'),
(12, 17, 'Ambiente 03', 'AMB-17-01', 'temperatura,humedad,co2',    '21.2,45,520',    5, 'Laboratorio 101', 1, 'FIUBA', '2026-03-05 09:15:00'),

-- Dispositivo 18 "Planta 01" (Planta Norte, TechCorp) -> 3+2+3+2 = 10 mediciones
(13, 18, 'Planta 01', 'PLT-18-01', 'temperatura,vibracion,modo_ahorro', '26.0,0.015,activado', 6, 'Planta Norte', 2, 'TechCorp', '2026-03-02 07:45:00'),
(14, 18, 'Planta 01', 'PLT-18-01', 'temperatura,vibracion',             '26.4,0.018',          6, 'Planta Norte', 2, 'TechCorp', '2026-03-03 07:45:00'),
(15, 18, 'Planta 01', 'PLT-18-01', 'temperatura,vibracion,modo_ahorro', '26.7,0.014,activado', 6, 'Planta Norte', 2, 'TechCorp', '2026-03-04 07:45:00'),
(16, 18, 'Planta 01', 'PLT-18-01', 'temperatura,vibracion',             '27.0,0.020',          6, 'Planta Norte', 2, 'TechCorp', '2026-03-05 07:45:00'),

-- Dispositivo 19 "Depósito 01" (Depósito Sur, TechCorp) -> 3+2+3+2 = 10 mediciones
(17, 19, 'Depósito 01', 'DEP-19-01', 'temperatura,humedad,modo_ahorro', '18.2,65,desactivado', 7, 'Depósito Sur', 2, 'TechCorp', '2026-03-02 14:20:00'),
(18, 19, 'Depósito 01', 'DEP-19-01', 'temperatura,humedad',              '18.5,64',             7, 'Depósito Sur', 2, 'TechCorp', '2026-03-03 14:20:00'),
(19, 19, 'Depósito 01', 'DEP-19-01', 'temperatura,humedad,modo_ahorro', '18.8,63,activado',    7, 'Depósito Sur', 2, 'TechCorp', '2026-03-04 14:20:00'),
(20, 19, 'Depósito 01', 'DEP-19-01', 'temperatura,humedad',              '19.0,62',             7, 'Depósito Sur', 2, 'TechCorp', '2026-03-05 14:20:00')

ON CONFLICT (id) DO UPDATE SET
    dispositivo_id = EXCLUDED.dispositivo_id,
    dispositivo_nombre = EXCLUDED.dispositivo_nombre,
    numero_serie = EXCLUDED.numero_serie,
    variables = EXCLUDED.variables,
    valores = EXCLUDED.valores,
    ubicacion_id = EXCLUDED.ubicacion_id,
    ubicacion_nombre = EXCLUDED.ubicacion_nombre,
    organizacion_id = EXCLUDED.organizacion_id,
    organizacion_nombre = EXCLUDED.organizacion_nombre,
    registrado_en = EXCLUDED.registrado_en;

-- Mantiene la secuencia del SERIAL alineada con los id explícitos insertados
-- arriba, para que cualquier INSERT posterior sin id explícito continúe en 21.
SELECT setval(pg_get_serial_sequence('registro_ambiental', 'id'), (SELECT MAX(id) FROM registro_ambiental));
