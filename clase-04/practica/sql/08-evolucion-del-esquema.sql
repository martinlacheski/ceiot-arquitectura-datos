-- CONTEXTO
-- Ejecutar después de sql/02-normalizacion.sql. Un requisito nuevo llega
-- cuando la base ya tiene datos: registrar la versión de firmware de cada
-- dispositivo. ALTER TABLE agrega la columna sin perder filas existentes;
-- el desafío real es decidir qué valor toman las filas que ya estaban.

-- EJEMPLO EJECUTABLE 1: agregar la columna nueva.
ALTER TABLE dispositivos ADD COLUMN IF NOT EXISTS firmware_version TEXT;

SELECT id, nombre, firmware_version FROM dispositivos ORDER BY id ASC;

-- OBSERVACIÓN ESPERADA
-- Los 5 dispositivos ya existentes quedan con firmware_version en NULL: ese
-- es el backfill por defecto de una columna nueva sin DEFAULT. NULL aquí
-- significa "dato desconocido todavía", no "sin firmware".

-- EJEMPLO EJECUTABLE 2: backfill real, pero solo para los dispositivos de los
-- que efectivamente se conoce la versión instalada (backfill parcial, algo
-- muy común cuando el dato nuevo no está disponible para todo el historial).
UPDATE dispositivos SET firmware_version = '1.4.0' WHERE id = 15;
UPDATE dispositivos SET firmware_version = '1.4.0' WHERE id = 17;
UPDATE dispositivos SET firmware_version = '2.1.0' WHERE id = 19;

SELECT id, nombre, firmware_version
FROM dispositivos
ORDER BY id ASC;

-- OBSERVACIÓN ESPERADA
-- Los dispositivos 15, 17 y 19 muestran versión; 16 y 18 siguen en NULL
-- porque todavía no se relevó su firmware. Ambos casos son válidos: una
-- migración de esquema no obliga a completar todos los datos el mismo día.

-- EJEMPLO EJECUTABLE 3: distinguir dispositivos con y sin dato relevado.
SELECT
    COUNT(*) FILTER (WHERE firmware_version IS NOT NULL) AS con_firmware_conocido,
    COUNT(*) FILTER (WHERE firmware_version IS NULL) AS pendiente_de_relevar
FROM dispositivos;

-- OBSERVACIÓN ESPERADA
-- con_firmware_conocido = 3, pendiente_de_relevar = 2.

-- MIGRACIÓN CONCEPTUAL (registro en comentario, no una herramienta real de
-- migraciones): documenta el orden en que fue evolucionando este esquema a
-- lo largo de la práctica, tal como se llevaría un changelog de esquema real.
--
-- v1 (database/01-schema.sql): registro_ambiental plano, denormalizado,
--    punto de partida.
-- v2 (sql/02-normalizacion.sql): se crean organizaciones, ubicaciones,
--    dispositivos y mediciones; se agrega dispositivos.medicion_count en
--    sql/03-desnormalizacion-justificada.sql.
-- v3 (sql/07-json-y-jsonb.sql): se agrega dispositivos.configuracion JSONB
--    para parámetros variables por dispositivo.
-- v4 (este archivo): se agrega dispositivos.firmware_version TEXT, con
--    backfill parcial documentado arriba.
-- v5 (sql/04-indices.sql): se agregan mediciones_dispositivo_id_idx y
--    mediciones_dispositivo_id_timestamp_idx (aplicado antes en el recorrido
--    numérico de archivos, pero registrado aquí para dejar el changelog
--    completo en un solo lugar).

-- VARIACIONES SEGURAS
-- Completar firmware_version = '2.1.0' también para el dispositivo 16 y
-- volver a ejecutar el EJEMPLO EJECUTABLE 3 para ver cómo cambian los conteos.
-- Agregar una columna nueva ALTER TABLE dispositivos ADD COLUMN IF NOT EXISTS
-- ultima_calibracion DATE y repetir el mismo análisis de backfill parcial.

-- RECUPERACIÓN
-- No hace falta: ALTER TABLE ... ADD COLUMN IF NOT EXISTS y los UPDATE por id
-- son repetibles sin duplicar ni perder datos.
