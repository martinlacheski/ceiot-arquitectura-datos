-- CONTEXTO
-- Este archivo deriva el modelo normalizado a partir de registro_ambiental,
-- en tres etapas explícitas: 1FN, 2FN y 3FN. Cada etapa crea la tabla que
-- corresponde, la puebla desde registro_ambiental y verifica con un COUNT(*)
-- el número de filas esperado (documentado también en el README). El archivo
-- es idempotente: puede ejecutarse varias veces sin duplicar datos ni fallar
-- por objetos ya existentes (CREATE TABLE IF NOT EXISTS, ON CONFLICT DO
-- NOTHING y bloques DO que ignoran restricciones ya creadas).
--
-- Modelo final: organizaciones -> ubicaciones -> dispositivos -> mediciones.

-- ============================================================
-- ETAPA 1FN: eliminar el grupo repetitivo (variables, valores)
-- ============================================================
-- "variables" y "valores" empaquetan varias mediciones por fila (viola 1FN).
-- Se desdoblan en una fila por (dispositivo_id, timestamp, variable, valor),
-- que es además la clave natural detectada en 01-dependencias-y-redundancia.sql.
-- Nota de simplificación pedagógica: para no repetir un paso intermedio,
-- esta etapa proyecta directamente las columnas mínimas de la futura tabla
-- mediciones (no arrastra dispositivo_nombre/ubicacion_nombre, que ya se
-- identificaron como redundantes). En una migración real conviene primero
-- conservar todas las columnas y depurarlas en pasos separados.

CREATE TABLE IF NOT EXISTS mediciones (
    id SERIAL PRIMARY KEY,
    dispositivo_id INTEGER NOT NULL,
    "timestamp" TIMESTAMP NOT NULL,
    variable TEXT NOT NULL,
    valor TEXT NOT NULL,
    UNIQUE (dispositivo_id, "timestamp", variable)
);

COMMENT ON CONSTRAINT mediciones_dispositivo_id_timestamp_variable_key ON mediciones IS
    'Materializa la clave natural (dispositivo_id, timestamp, variable) hallada '
    'en el análisis de 1FN; también sirve de objetivo para ON CONFLICT.';

INSERT INTO mediciones (dispositivo_id, "timestamp", variable, valor)
SELECT
    r.dispositivo_id,
    r.registrado_en,
    t.variable,
    t.valor
FROM registro_ambiental AS r
CROSS JOIN LATERAL unnest(
    string_to_array(r.variables, ','),
    string_to_array(r.valores, ',')
) AS t(variable, valor)
ORDER BY r.id
ON CONFLICT (dispositivo_id, "timestamp", variable) DO NOTHING;

-- VERIFICACIÓN 1FN
SELECT COUNT(*) AS mediciones_totales FROM mediciones;
-- OBSERVACIÓN ESPERADA: 50.

SELECT dispositivo_id, COUNT(*) AS mediciones_por_dispositivo
FROM mediciones
GROUP BY dispositivo_id
ORDER BY dispositivo_id ASC;
-- OBSERVACIÓN ESPERADA: 15 -> 10, 16 -> 8, 17 -> 12, 18 -> 10, 19 -> 10.

-- ============================================================
-- ETAPA 2FN: eliminar dependencias parciales de la clave natural
-- ============================================================
-- Sobre la clave (dispositivo_id, timestamp, variable), dispositivo_nombre y
-- numero_serie dependen solo de dispositivo_id (dependencia parcial): se
-- extraen a su propia tabla. ubicacion_id todavía no tiene FK porque
-- ubicaciones se crea recién en la etapa 3FN.

CREATE TABLE IF NOT EXISTS dispositivos (
    id INTEGER PRIMARY KEY,
    ubicacion_id INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    numero_serie TEXT NOT NULL UNIQUE
);

INSERT INTO dispositivos (id, ubicacion_id, nombre, numero_serie)
SELECT DISTINCT
    dispositivo_id,
    ubicacion_id,
    dispositivo_nombre,
    numero_serie
FROM registro_ambiental
ORDER BY dispositivo_id
ON CONFLICT (id) DO NOTHING;

-- Ahora que dispositivos existe, mediciones.dispositivo_id puede referenciarlo.
DO $$
BEGIN
    ALTER TABLE mediciones
        ADD CONSTRAINT mediciones_dispositivo_id_fkey
        FOREIGN KEY (dispositivo_id) REFERENCES dispositivos(id) ON DELETE RESTRICT;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- VERIFICACIÓN 2FN
SELECT COUNT(*) AS dispositivos_totales FROM dispositivos;
-- OBSERVACIÓN ESPERADA: 5.

-- ============================================================
-- ETAPA 3FN: eliminar dependencias transitivas
-- ============================================================
-- ubicacion_nombre depende de ubicacion_id, no directamente de dispositivo_id
-- (dependencia transitiva a través de dispositivos): se extrae ubicaciones.
-- Lo mismo ocurre con organizacion_nombre a través de organizacion_id: se
-- extrae organizaciones. Se crean en orden de dependencia: organizaciones
-- primero, luego ubicaciones (que la referencia).

CREATE TABLE IF NOT EXISTS organizaciones (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

INSERT INTO organizaciones (id, nombre)
SELECT DISTINCT organizacion_id, organizacion_nombre
FROM registro_ambiental
ORDER BY organizacion_id
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS ubicaciones (
    id INTEGER PRIMARY KEY,
    organizacion_id INTEGER NOT NULL,
    nombre TEXT NOT NULL
);

INSERT INTO ubicaciones (id, organizacion_id, nombre)
SELECT DISTINCT ubicacion_id, organizacion_id, ubicacion_nombre
FROM registro_ambiental
ORDER BY ubicacion_id
ON CONFLICT (id) DO NOTHING;

DO $$
BEGIN
    ALTER TABLE ubicaciones
        ADD CONSTRAINT ubicaciones_organizacion_id_fkey
        FOREIGN KEY (organizacion_id) REFERENCES organizaciones(id) ON DELETE RESTRICT;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE dispositivos
        ADD CONSTRAINT dispositivos_ubicacion_id_fkey
        FOREIGN KEY (ubicacion_id) REFERENCES ubicaciones(id) ON DELETE RESTRICT;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- VERIFICACIÓN 3FN
SELECT COUNT(*) AS organizaciones_totales FROM organizaciones;
-- OBSERVACIÓN ESPERADA: 2.

SELECT COUNT(*) AS ubicaciones_totales FROM ubicaciones;
-- OBSERVACIÓN ESPERADA: 4.

-- VERIFICACIÓN FINAL: recorrer el modelo completo con joins.
SELECT
    o.nombre AS organizacion,
    u.nombre AS ubicacion,
    d.nombre AS dispositivo,
    d.numero_serie,
    COUNT(m.id) AS mediciones
FROM organizaciones AS o
JOIN ubicaciones AS u ON u.organizacion_id = o.id
JOIN dispositivos AS d ON d.ubicacion_id = u.id
LEFT JOIN mediciones AS m ON m.dispositivo_id = d.id
GROUP BY o.nombre, u.nombre, d.nombre, d.numero_serie
ORDER BY o.nombre ASC, u.nombre ASC, d.nombre ASC;

-- OBSERVACIÓN ESPERADA
-- 5 filas (una por dispositivo). La suma de la columna "mediciones" da 50,
-- igual que el conteo total verificado en la etapa 1FN.
