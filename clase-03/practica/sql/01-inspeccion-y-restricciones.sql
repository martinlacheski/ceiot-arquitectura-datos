-- CONTEXTO
-- Primer recorrido: reconocer tablas, columnas, PK, FK y restricciones del modelo relacional.

-- EJEMPLO EJECUTABLE 1: tablas base del esquema public.
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- OBSERVACIÓN ESPERADA
-- Aparecen las ocho tablas IoT. Una tabla representa una relación; cada fila es una tupla.
-- Una columna es un atributo y su data_type define qué valores puede almacenar.

-- EJEMPLO EJECUTABLE 2: atributos de measurements.
SELECT
    ordinal_position,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'measurements'
ORDER BY ordinal_position;

-- OBSERVACIÓN ESPERADA
-- id es UUID; device_id, variable, value, unit y recorded_at no aceptan NULL.

-- EJEMPLO EJECUTABLE 3: PK, FK, UNIQUE y CHECK declarados.
SELECT
    relation.relname AS table_name,
    constraint_record.conname AS constraint_name,
    CASE constraint_record.contype
        WHEN 'p' THEN 'PRIMARY KEY'
        WHEN 'f' THEN 'FOREIGN KEY'
        WHEN 'u' THEN 'UNIQUE'
        WHEN 'c' THEN 'CHECK'
    END AS constraint_type,
    pg_get_constraintdef(constraint_record.oid) AS constraint_definition
FROM pg_constraint AS constraint_record
INNER JOIN pg_class AS relation
  ON relation.oid = constraint_record.conrelid
INNER JOIN pg_namespace AS schema_record
  ON schema_record.oid = relation.relnamespace
WHERE schema_record.nspname = 'public'
  AND relation.relname IN ('devices', 'measurements', 'organization_users')
  AND constraint_record.contype IN ('p', 'f', 'u', 'c')
ORDER BY relation.relname, constraint_type, constraint_record.conname;

-- OBSERVACIÓN ESPERADA
-- Cada restricción ocupa una sola fila. La PK compuesta de organization_users aparece
-- como PRIMARY KEY (organization_id, user_id); la FK de measurements muestra REFERENCES devices(id).

-- VARIACIONES SEGURAS
-- Cambiar la lista de table_name por ('locations', 'device_status_history').
-- Quitar el filtro de table_name para inspeccionar todo public.

-- RECUPERACIÓN
-- No hace falta: estas consultas solamente leen metadatos.
