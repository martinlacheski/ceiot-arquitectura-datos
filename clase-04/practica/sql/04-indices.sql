-- CONTEXTO
-- Ejecutar después de sql/02-normalizacion.sql. El patrón de consulta frecuente
-- de esta práctica es:
--   SELECT * FROM mediciones
--   WHERE dispositivo_id = ? AND timestamp >= ? AND timestamp < ?
--   ORDER BY timestamp;
-- Este archivo crea los índices que lo aceleran y discute selectividad.
-- El efecto sobre el plan de ejecución se mide en sql/05-planes-de-ejecucion.sql,
-- que primero elimina estos índices para reproducir el "antes" y luego los
-- vuelve a crear igual que aquí para medir el "después".

-- EJEMPLO EJECUTABLE 1: índice simple sobre la columna de igualdad.
CREATE INDEX IF NOT EXISTS mediciones_dispositivo_id_idx ON mediciones (dispositivo_id);

-- OBSERVACIÓN ESPERADA
-- Sirve para filtros de igualdad por dispositivo_id solo, por ejemplo
-- "WHERE dispositivo_id = 17" sin condición de fecha. No ayuda a ordenar
-- por timestamp ni a acotar el rango de fechas dentro de un mismo dispositivo.

-- EJEMPLO EJECUTABLE 2: índice compuesto que sigue el orden de la consulta frecuente.
CREATE INDEX IF NOT EXISTS mediciones_dispositivo_id_timestamp_idx
    ON mediciones (dispositivo_id, "timestamp");

-- OBSERVACIÓN ESPERADA
-- El orden de columnas importa: la columna de igualdad (dispositivo_id) va
-- primero y la columna de rango/orden (timestamp) va segunda. Esto permite
-- que Postgres ubique de una vez el bloque de filas de un dispositivo y las
-- recorra ya ordenadas por timestamp, sin un sort adicional. Un índice
-- (timestamp, dispositivo_id) invertido no serviría igual: la igualdad debe
-- ir primero para aprovechar el prefijo del índice B-tree.
--
-- Nota: por la regla de "prefijo más a la izquierda" (leftmost prefix), este
-- índice compuesto también puede resolver consultas que solo filtran por
-- dispositivo_id, igual que el índice simple del ejemplo 1. En un esquema de
-- producción probablemente se eliminaría el índice simple para no duplicar
-- mantenimiento; se conservan ambos aquí únicamente para poder compararlos
-- en sql/05-planes-de-ejecucion.sql.

-- EJEMPLO EJECUTABLE 3: selectividad alta (numero_serie es único por dispositivo).
SELECT COUNT(*) AS dispositivos_totales,
       (SELECT COUNT(*) FROM dispositivos WHERE numero_serie = 'AMB-17-01') AS coincidencias
FROM dispositivos;

-- OBSERVACIÓN ESPERADA
-- 1 coincidencia sobre 5 dispositivos (20%) y, al ser un valor único (UNIQUE),
-- identifica una sola fila sin ambigüedad: alta selectividad. Un índice sobre
-- una columna así de selectiva es muy eficiente porque descarta casi todas
-- las filas de una vez.

-- EJEMPLO EJECUTABLE 4: selectividad baja (variable solo toma unos pocos valores).
SELECT COUNT(*) AS mediciones_totales,
       (SELECT COUNT(*) FROM mediciones WHERE variable = 'temperatura') AS coincidencias
FROM mediciones;

-- OBSERVACIÓN ESPERADA
-- 20 coincidencias sobre 50 mediciones (40%): baja selectividad. Un índice
-- solo sobre "variable" descartaría poco menos de la mitad de las filas y
-- aportaría poco frente a un Seq Scan; por eso no se crea un índice dedicado
-- a esa columna en esta práctica.

-- VARIACIONES SEGURAS
-- Repetir el ejemplo 4 con variable = 'co2' (6 de 50, todavía baja selectividad
-- relativa aunque menor) y con variable = 'vibracion' (4 de 50).
-- Listar los índices creados sobre mediciones:
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'mediciones'
ORDER BY indexname;

-- RECUPERACIÓN
-- No hace falta: CREATE INDEX IF NOT EXISTS es repetible sin efectos duplicados.
