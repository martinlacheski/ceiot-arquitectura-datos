-- CONTEXTO
-- Ejecutar después de sql/02-normalizacion.sql. Cada modelo de dispositivo
-- admite parámetros de configuración distintos (intervalo de muestreo, modo
-- de ahorro, umbrales por variable). Modelarlos como columnas fijas obligaría
-- a agregar una columna nueva por cada parámetro que aparezca en un modelo
-- futuro, con NULL para todos los dispositivos que no lo usan. JSONB permite
-- guardar formas distintas por fila sin ese costo de esquema.

-- numero_serie sigue siendo una columna propia: es un atributo simple, igual
-- para todos los dispositivos y se usa en igualdad/JOIN, así que no gana nada
-- estando en JSONB. configuracion, en cambio, varía de forma real entre
-- dispositivos: ahí sí se justifica JSONB.

ALTER TABLE dispositivos ADD COLUMN IF NOT EXISTS configuracion JSONB;

-- EJEMPLO EJECUTABLE 1: cargar configuraciones con formas distintas por dispositivo.
UPDATE dispositivos SET configuracion = '{"intervalo": 30, "umbral_temperatura": 28}'::JSONB
WHERE id = 15;

UPDATE dispositivos SET configuracion = '{"intervalo": 45, "umbral_temperatura": 30}'::JSONB
WHERE id = 16;

UPDATE dispositivos SET configuracion = '{"intervalo": 20, "umbral_temperatura": 26, "umbral_co2": 800}'::JSONB
WHERE id = 17;

UPDATE dispositivos SET configuracion = '{"intervalo": 10, "modo": "eco", "presion_habilitada": true}'::JSONB
WHERE id = 18;

UPDATE dispositivos SET configuracion = '{"intervalo": 15, "modo": "eco", "umbral_humedad": 70}'::JSONB
WHERE id = 19;

SELECT id, nombre, configuracion FROM dispositivos ORDER BY id ASC;

-- OBSERVACIÓN ESPERADA
-- Los dispositivos 15, 16 y 17 (ambientales) tienen umbral_temperatura y
-- opcionalmente umbral_co2; los dispositivos 18 y 19 (industriales) tienen
-- "modo" y variantes propias. No hay dos configuraciones con exactamente las
-- mismas claves: eso es lo que JSONB modela sin forzar columnas NULL.

-- EJEMPLO EJECUTABLE 2: leer un campo puntual con el operador ->>.
SELECT id, nombre, configuracion ->> 'intervalo' AS intervalo_segundos
FROM dispositivos
ORDER BY id ASC;

-- OBSERVACIÓN ESPERADA
-- ->> devuelve el valor como texto (por eso intervalo_segundos se ve como
-- '30', '45', etc. entre comillas si se inspecciona el tipo). Para operar
-- numéricamente habría que castear: (configuracion ->> 'intervalo')::INTEGER.

-- EJEMPLO EJECUTABLE 3: filtrar por un campo que solo existe en algunas filas.
SELECT id, nombre, configuracion ->> 'modo' AS modo
FROM dispositivos
WHERE configuracion ->> 'modo' = 'eco'
ORDER BY id ASC;

-- OBSERVACIÓN ESPERADA
-- Solo los dispositivos 18 y 19 tienen la clave "modo"; los demás no
-- aparecen porque ->> sobre una clave inexistente da NULL, y NULL = 'eco' no
-- es verdadero. No hizo falta ALTER TABLE para agregar este campo nuevo.

-- EJEMPLO EJECUTABLE 4: operador de contención @> para buscar por sub-documento.
SELECT id, nombre, configuracion
FROM dispositivos
WHERE configuracion @> '{"presion_habilitada": true}'::JSONB;

-- OBSERVACIÓN ESPERADA
-- Devuelve solo el dispositivo 18: @> compara el JSON completo, no solo un
-- campo de texto, y es útil para filtros exactos sobre sub-documentos.

-- EJEMPLO EJECUTABLE 5 (variación segura ejecutable): índice GIN para acelerar
-- búsquedas por contenido JSONB en tablas mucho más grandes que esta.
CREATE INDEX IF NOT EXISTS dispositivos_configuracion_gin_idx
    ON dispositivos USING GIN (configuracion);

-- OBSERVACIÓN ESPERADA
-- Con solo 5 dispositivos el índice no cambia el plan (el planificador sigue
-- prefiriendo Seq Scan, igual que en sql/05-planes-de-ejecucion.sql), pero es
-- la forma estándar de indexar columnas JSONB cuando la tabla crece y se
-- filtra frecuentemente con @> o ?.

-- VARIACIONES SEGURAS
-- Agregar "umbral_humedad" a la configuración del dispositivo 15 con un UPDATE
-- que use jsonb_set(configuracion, '{umbral_humedad}', '65') en vez de reescribir todo el JSON.
-- Probar WHERE configuracion ? 'umbral_co2' para verificar existencia de una clave.

-- RECUPERACIÓN
-- No hace falta: ALTER TABLE ... ADD COLUMN IF NOT EXISTS y los UPDATE son
-- repetibles, y CREATE INDEX IF NOT EXISTS no duplica el índice.
