-- Punto de partida intencionalmente DESNORMALIZADO para la práctica de Clase 4.
-- registro_ambiental mezcla en una sola fila datos de dispositivo, ubicación,
-- organización y una lista de variables/valores separada por comas. El objetivo
-- pedagógico es observar redundancia y violaciones de 1FN antes de normalizar
-- en sql/02-normalizacion.sql. No se crean aquí las tablas normalizadas
-- (organizaciones, ubicaciones, dispositivos, mediciones): eso es precisamente
-- lo que el recorrido de normalización construye paso a paso.
CREATE TABLE IF NOT EXISTS registro_ambiental (
    id SERIAL PRIMARY KEY,
    dispositivo_id INTEGER NOT NULL,
    dispositivo_nombre TEXT NOT NULL,
    numero_serie TEXT NOT NULL,
    variables TEXT NOT NULL,
    valores TEXT NOT NULL,
    ubicacion_id INTEGER NOT NULL,
    ubicacion_nombre TEXT NOT NULL,
    organizacion_id INTEGER NOT NULL,
    organizacion_nombre TEXT NOT NULL,
    registrado_en TIMESTAMP NOT NULL
);

COMMENT ON TABLE registro_ambiental IS
    'Tabla plana desnormalizada de origen. dispositivo_nombre, numero_serie, '
    'ubicacion_nombre, organizacion_nombre y organizacion_id se repiten en cada '
    'fila; variables/valores violan 1FN al empaquetar varias mediciones por fila.';
