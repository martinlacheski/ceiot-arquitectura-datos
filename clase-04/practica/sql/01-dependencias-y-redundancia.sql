-- CONTEXTO
-- registro_ambiental es una tabla plana desnormalizada. Antes de normalizar,
-- conviene hacer observable el problema: qué datos se repiten y por qué esa
-- repetición es peligrosa (anomalías de actualización, inserción y borrado).
-- Todas las consultas de este archivo son de solo lectura.

-- EJEMPLO EJECUTABLE 1: la misma información de dispositivo se repite en cada fila.
SELECT dispositivo_id, dispositivo_nombre, numero_serie, ubicacion_id, ubicacion_nombre
FROM registro_ambiental
WHERE dispositivo_id = 15
ORDER BY registrado_en ASC;

-- OBSERVACIÓN ESPERADA
-- Aparecen 4 filas y las cinco columnas repiten el mismo valor en cada una.
-- dispositivo_nombre, numero_serie, ubicacion_id y ubicacion_nombre dependen
-- funcionalmente de dispositivo_id, no del par (dispositivo_id, registrado_en).
-- Notación de dependencia funcional: dispositivo_id -> dispositivo_nombre, numero_serie, ubicacion_id.

-- EJEMPLO EJECUTABLE 2: el nombre de la ubicación se repite una vez por cada dispositivo que aloja.
SELECT ubicacion_id, ubicacion_nombre, dispositivo_id, dispositivo_nombre
FROM registro_ambiental
WHERE ubicacion_id = 4
GROUP BY ubicacion_id, ubicacion_nombre, dispositivo_id, dispositivo_nombre
ORDER BY dispositivo_id ASC;

-- OBSERVACIÓN ESPERADA
-- 'Aula 204' aparece asociada a los dispositivos 15 y 16: la misma ubicación
-- se repite tantas veces como dispositivos y lecturas tenga. Dependencia:
-- ubicacion_id -> ubicacion_nombre (independiente de dispositivo_id).

-- EJEMPLO EJECUTABLE 3: contar la redundancia real en toda la tabla.
SELECT
    COUNT(*) AS filas_totales,
    COUNT(DISTINCT dispositivo_id) AS dispositivos_distintos,
    COUNT(DISTINCT ubicacion_id) AS ubicaciones_distintas,
    COUNT(DISTINCT organizacion_id) AS organizaciones_distintas
FROM registro_ambiental;

-- OBSERVACIÓN ESPERADA
-- 20 filas contra apenas 5 dispositivos, 4 ubicaciones y 2 organizaciones:
-- cada valor de dispositivo/ubicacion/organizacion se guarda varias veces.

-- EJEMPLO EJECUTABLE 4: riesgo de anomalía de actualización (solo lectura, no se ejecuta el UPDATE).
-- Si "Aula 204" cambiara de nombre habría que tocar TODAS las filas que la
-- mencionan. La siguiente consulta muestra cuántas filas quedarían inconsistentes
-- si se actualizara una sola de ellas y se olvidaran las demás.
SELECT COUNT(*) AS filas_que_habria_que_actualizar
FROM registro_ambiental
WHERE ubicacion_id = 4;

-- OBSERVACIÓN ESPERADA
-- 8 filas comparten ubicacion_id = 4. Un UPDATE parcial (por ejemplo, solo
-- sobre las filas del dispositivo 15) dejaría el nombre de la ubicación
-- inconsistente entre filas que deberían decir lo mismo: esa es la anomalía
-- de actualización que la normalización elimina.

-- EJEMPLO EJECUTABLE 5: la columna "variables" empaqueta varias mediciones en un solo valor (viola 1FN).
SELECT id, dispositivo_id, variables, valores, registrado_en
FROM registro_ambiental
WHERE dispositivo_id = 17
ORDER BY registrado_en ASC;

-- OBSERVACIÓN ESPERADA
-- "variables" y "valores" contienen listas separadas por comas
-- ('temperatura,humedad,co2'): cada fila describe en realidad tres mediciones
-- distintas empaquetadas como si fueran un solo atributo atómico. Esa es
-- exactamente la violación de 1FN que sql/02-normalizacion.sql resuelve.

-- EJEMPLO EJECUTABLE 6: anomalía de borrado. Si se eliminara la única fila
-- de un dispositivo se perdería también el dato de su ubicación y organización.
SELECT dispositivo_id, COUNT(*) AS filas
FROM registro_ambiental
GROUP BY dispositivo_id
ORDER BY dispositivo_id ASC;

-- OBSERVACIÓN ESPERADA
-- Todos los dispositivos de este seed tienen varias filas, pero si alguno
-- tuviera una sola y esa fila se borrara, desaparecería junto con ella el
-- único registro de a qué ubicación y organización pertenecía ese
-- dispositivo: la información de dispositivo/ubicación no debería depender
-- de la existencia de una medición puntual.

-- VARIACIONES SEGURAS
-- Repetir el ejemplo 1 con dispositivo_id = 18 o 19.
-- En el ejemplo 3, agregar COUNT(DISTINCT numero_serie) y comparar contra dispositivos_distintos.
-- En el ejemplo 5, probar con dispositivo_id = 18 para ver la variable 'modo_ahorro'.

-- RECUPERACIÓN
-- No hace falta: todos los ejemplos son SELECT.
