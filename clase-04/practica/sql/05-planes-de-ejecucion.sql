-- CONTEXTO
-- Ejecutar después de sql/04-indices.sql. EXPLAIN muestra el plan estimado sin
-- ejecutar la consulta; EXPLAIN ANALYZE la ejecuta de verdad y agrega tiempos
-- y filas reales. Este archivo mide el patrón de consulta frecuente:
--   SELECT * FROM mediciones
--   WHERE dispositivo_id = 17 AND timestamp >= ... AND timestamp < ...
--   ORDER BY timestamp;
-- primero SIN los índices de 04 (los elimina temporalmente para reproducir el
-- "antes") y después los vuelve a crear igual que 04 para medir el "después".
-- Al terminar este archivo los índices quedan creados, igual que si solo se
-- hubiera ejecutado 04-indices.sql.

-- ============================================================
-- PARTE 1: ANTES, sin índices sobre mediciones
-- ============================================================
DROP INDEX IF EXISTS mediciones_dispositivo_id_timestamp_idx;
DROP INDEX IF EXISTS mediciones_dispositivo_id_idx;

EXPLAIN ANALYZE
SELECT *
FROM mediciones
WHERE dispositivo_id = 17
  AND "timestamp" >= '2026-03-02 00:00:00'
  AND "timestamp" < '2026-03-06 00:00:00'
ORDER BY "timestamp";

-- OBSERVACIÓN ESPERADA
-- Sin índices, el plan es un Seq Scan sobre mediciones (con un Sort aparte
-- para ORDER BY): recorre las 50 filas de la tabla y filtra al vuelo. Es el
-- comportamiento correcto y esperado sin índice, no una falla. "Rows" en el
-- nodo de salida debería mostrar 12 filas (las del dispositivo 17).

-- ============================================================
-- PARTE 2: DESPUÉS, con los índices de 04-indices.sql recreados
-- ============================================================
CREATE INDEX IF NOT EXISTS mediciones_dispositivo_id_idx ON mediciones (dispositivo_id);
CREATE INDEX IF NOT EXISTS mediciones_dispositivo_id_timestamp_idx
    ON mediciones (dispositivo_id, "timestamp");

EXPLAIN ANALYZE
SELECT *
FROM mediciones
WHERE dispositivo_id = 17
  AND "timestamp" >= '2026-03-02 00:00:00'
  AND "timestamp" < '2026-03-06 00:00:00'
ORDER BY "timestamp";

-- OBSERVACIÓN ESPERADA
-- mediciones tiene apenas 50 filas: el planificador de PostgreSQL puede seguir
-- eligiendo Seq Scan aunque el índice exista, porque para una tabla tan chica
-- recorrerla entera es más barato que ir y volver al índice. Esto es correcto:
-- la existencia de un índice no garantiza su uso, el costo estimado decide.
-- Para observar igual el plan alternativo con fines didácticos, se fuerza a
-- continuación desactivar Seq Scan para esta sesión (NUNCA hacer esto en
-- producción; es solo una forma de comparar planes en una tabla pequeña).
SET enable_seqscan = off;

EXPLAIN ANALYZE
SELECT *
FROM mediciones
WHERE dispositivo_id = 17
  AND "timestamp" >= '2026-03-02 00:00:00'
  AND "timestamp" < '2026-03-06 00:00:00'
ORDER BY "timestamp";

-- OBSERVACIÓN ESPERADA
-- Con Seq Scan deshabilitado, el plan pasa a usar
-- mediciones_dispositivo_id_timestamp_idx con un Index Scan (o Index Only
-- Scan si "*" no fuerza acceso a la tabla): el nodo ya entrega las filas
-- ordenadas por timestamp sin un Sort adicional, porque el índice compuesto
-- las guarda en ese orden dentro de cada dispositivo_id. "Rows" debería
-- seguir mostrando 12.

-- Restaurar el comportamiento normal del planificador para el resto de la sesión.
SET enable_seqscan = on;

-- VARIACIONES SEGURAS
-- Repetir ambas partes con dispositivo_id = 15 (10 filas esperadas) o 18 (10 filas).
-- Quitar el ORDER BY y comparar si sigue apareciendo un nodo Sort en el plan.
-- Ejecutar solo EXPLAIN (sin ANALYZE) y notar que no aparecen tiempos reales
-- ("actual time"), solo el costo estimado.

-- RECUPERACIÓN
-- No hace falta: la Parte 2 vuelve a crear los mismos índices que
-- sql/04-indices.sql, y enable_seqscan queda restaurado a "on" al final.
