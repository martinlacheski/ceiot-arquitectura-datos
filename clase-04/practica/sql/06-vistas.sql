-- CONTEXTO
-- Ejecutar después de sql/02-normalizacion.sql. Una VIEW es una consulta
-- guardada: se recalcula en cada SELECT y siempre refleja los datos actuales.
-- Una MATERIALIZED VIEW guarda el resultado físicamente: es más rápida de
-- leer pero queda desactualizada hasta que se ejecuta REFRESH a propósito.

-- EJEMPLO EJECUTABLE 1: VIEW con contexto legible (join de mediciones + dispositivo + ubicación).
CREATE OR REPLACE VIEW mediciones_con_contexto AS
SELECT
    m."timestamp",
    m.variable,
    m.valor,
    d.nombre AS dispositivo,
    u.nombre AS ubicacion
FROM mediciones m
JOIN dispositivos d ON m.dispositivo_id = d.id
LEFT JOIN ubicaciones u ON d.ubicacion_id = u.id;

SELECT * FROM mediciones_con_contexto
ORDER BY dispositivo ASC, "timestamp" ASC
LIMIT 5;

-- OBSERVACIÓN ESPERADA
-- Cada fila muestra la medición junto al nombre legible del dispositivo y su
-- ubicación, sin que el usuario de la vista tenga que escribir los joins.
-- El LEFT JOIN a ubicaciones evita perder filas si algún dispositivo quedara
-- sin ubicación asignada; en este seed todos la tienen.

-- EJEMPLO EJECUTABLE 2: MATERIALIZED VIEW con un agregado costoso de recalcular siempre.
-- CREATE OR REPLACE no existe para vistas materializadas: se recrea con DROP + CREATE.
DROP MATERIALIZED VIEW IF EXISTS resumen_mediciones;

CREATE MATERIALIZED VIEW resumen_mediciones AS
SELECT
    dispositivo_id,
    variable,
    AVG(valor::NUMERIC) AS promedio
FROM mediciones
WHERE valor ~ '^-?[0-9]+(\.[0-9]+)?$'
GROUP BY dispositivo_id, variable;

-- Nota: el filtro con ~ excluye valores no numéricos como 'activado' o
-- 'desactivado' (la variable modo_ahorro), porque promediar texto no tiene
-- sentido; solo se promedian variables realmente numéricas.

SELECT * FROM resumen_mediciones
ORDER BY dispositivo_id ASC, variable ASC;

-- OBSERVACIÓN ESPERADA
-- Un promedio por (dispositivo_id, variable) ya calculado y guardado, listo
-- para leer sin repetir el AVG ni el filtro cada vez.

-- EJEMPLO EJECUTABLE 3: la VIEW se actualiza sola; la MATERIALIZED VIEW no.
INSERT INTO mediciones (dispositivo_id, "timestamp", variable, valor)
VALUES (15, '2026-03-06 10:30:00', 'temperatura', '30.0')
ON CONFLICT (dispositivo_id, "timestamp", variable) DO NOTHING;

SELECT COUNT(*) AS filas_en_vista
FROM mediciones_con_contexto
WHERE dispositivo = 'Ambiente 01';

SELECT promedio AS promedio_materializado_sin_refresh
FROM resumen_mediciones
WHERE dispositivo_id = 15 AND variable = 'temperatura';

-- OBSERVACIÓN ESPERADA
-- filas_en_vista ya incluye la medición recién insertada (la VIEW siempre
-- recalcula), pero promedio_materializado_sin_refresh todavía muestra el
-- promedio ANTERIOR a esa medición: la vista materializada quedó desactualizada.

REFRESH MATERIALIZED VIEW resumen_mediciones;

SELECT promedio AS promedio_materializado_despues_de_refresh
FROM resumen_mediciones
WHERE dispositivo_id = 15 AND variable = 'temperatura';

-- OBSERVACIÓN ESPERADA
-- Después de REFRESH, promedio_materializado_despues_de_refresh ya incorpora
-- la medición nueva. REFRESH recalcula todo el contenido de la vista.

-- RECUPERACIÓN: quitar la medición de demostración y refrescar de nuevo para
-- dejar resumen_mediciones exactamente como al empezar el archivo.
DELETE FROM mediciones
WHERE dispositivo_id = 15
  AND "timestamp" = '2026-03-06 10:30:00'
  AND variable = 'temperatura';

REFRESH MATERIALIZED VIEW resumen_mediciones;

SELECT COUNT(*) AS mediciones_totales FROM mediciones;
-- OBSERVACIÓN ESPERADA: 50 (de nuevo).

-- VARIACIONES SEGURAS
-- Cambiar mediciones_con_contexto para agregar d.numero_serie.
-- Agregar a resumen_mediciones MIN(valor::NUMERIC) y MAX(valor::NUMERIC).

-- La VIEW y la MATERIALIZED VIEW quedan creadas de forma permanente para las
-- siguientes prácticas; solo la fila de demostración del ejemplo 3 se retira.
