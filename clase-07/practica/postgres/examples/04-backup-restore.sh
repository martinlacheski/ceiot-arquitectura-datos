#!/bin/sh
# Backup lógico y restauración (slides 49-53).
#
# Se ejecuta DENTRO del contenedor postgres (usa pg_dump/pg_restore de la imagen):
#
#   docker compose --env-file .env -f compose.yaml exec postgres sh /lab/examples/04-backup-restore.sh
#   docker compose --env-file .env -f compose.yaml exec postgres sh /lab/examples/04-backup-restore.sh recuperar
#
# Sin argumento: respaldo (pg_dump -Fc) -> restauración en una base nueva
#   (ceiot_class7_restored) -> comparación de filas por tabla.
# Con "recuperar": segunda parte del escenario "error humano". Antes hay que
#   correr 04-error-humano.sql, que borra las mediciones de PLT-002; acá se
#   rescatan desde la base restaurada sin tocar el resto de los datos.
#
# El dump queda en el volumen postgres_backups (/home/postgres/pgdata/backup),
# que sobrevive a `docker compose down` (no a `down -v`).
#
# Es repetible: recrea la base restaurada cada vez.
set -eu

DB="${POSTGRES_DB:?POSTGRES_DB no está definida}"
RESTORED="${DB}_restored"
BACKUP_DIR="/home/postgres/pgdata/backup"
DUMP="${BACKUP_DIR}/${DB}.dump"
export PGUSER="${POSTGRES_USER:?POSTGRES_USER no está definida}"
# Conexión por socket local (confianza en pg_hba.conf): no hace falta contraseña.

psql_db() { # psql_db <base> [args de psql...]
    _db="$1"; shift
    psql -X -v ON_ERROR_STOP=1 -d "$_db" "$@"
}

# Cuenta filas por tabla como dueño (el superusuario ignora RLS, ve todas las organizaciones).
COUNTS_SQL="SELECT 'organizations' AS tabla, count(*) AS filas FROM organizations
UNION ALL SELECT 'locations', count(*) FROM locations
UNION ALL SELECT 'devices', count(*) FROM devices
UNION ALL SELECT 'measurements', count(*) FROM measurements
UNION ALL SELECT 'manual_documents', count(*) FROM manual_documents
UNION ALL SELECT 'manual_chunks', count(*) FROM manual_chunks
ORDER BY 1"

if [ "${1:-}" = "recuperar" ]; then
    echo
    echo "=== Recuperación puntual: mediciones de PLT-002 desde ${RESTORED} ==="
    echo "Qué observar: antes del rescate PLT-002 tiene 0 filas; después vuelve a tener las del respaldo,"
    echo "y las demás filas no cambian (el INSERT ignora las que ya existen)."
    psql_db "$RESTORED" -Atc "SELECT 1 FROM measurements LIMIT 1" >/dev/null ||
        { echo "No existe ${RESTORED}: corré primero este script sin argumentos." >&2; exit 1; }
    psql_db "$DB" -c "SELECT count(*) AS plt002_antes FROM measurements WHERE device_id = 'PLT-002'"
    {
        echo "CREATE TEMP TABLE rescate (LIKE measurements);"
        echo "COPY rescate FROM STDIN;"
        # COPY ... TO STDOUT en la base restaurada alimenta el COPY ... FROM STDIN de la base viva.
        psql_db "$RESTORED" -c "COPY (SELECT * FROM measurements WHERE device_id = 'PLT-002') TO STDOUT"
        echo '\.'
        echo "INSERT INTO measurements
              SELECT r.* FROM rescate AS r
              WHERE NOT EXISTS (
                  SELECT 1 FROM measurements AS m
                  WHERE m.device_id = r.device_id
                    AND m.measured_at = r.measured_at
                    AND m.variable = r.variable);"
        echo "SELECT count(*) AS plt002_despues FROM measurements WHERE device_id = 'PLT-002';"
    } | psql_db "$DB"
    echo
    echo "Listo. Límite del método: sólo recupera lo que existía al momento del respaldo."
    exit 0
fi

echo "=== 1. Respaldo lógico: pg_dump -Fc de ${DB} ==="
echo "Qué observar: un único archivo comprimido (-Fc = formato custom) en el volumen de respaldos."
echo "(El aviso de claves foráneas circulares de continuous_agg es del catálogo interno de TimescaleDB: es normal.)"
mkdir -p "$BACKUP_DIR"
pg_dump -Fc -d "$DB" -f "$DUMP"
ls -lh "$DUMP"

echo
echo "=== 2. Base destino vacía: ${RESTORED} ==="
psql_db postgres -c "DROP DATABASE IF EXISTS ${RESTORED} WITH (FORCE)"
psql_db postgres -c "CREATE DATABASE ${RESTORED}"

echo
echo "=== 3. Restauración con el procedimiento de TimescaleDB ==="
echo "Qué observar: la extensión se crea ANTES; pre_restore pone la base en modo restauración,"
echo "pg_restore carga el dump y post_restore reactiva los jobs de la base."
psql_db "$RESTORED" -c "CREATE EXTENSION IF NOT EXISTS timescaledb"
psql_db "$RESTORED" -c "SELECT timescaledb_pre_restore()"
# No se usa --exit-on-error: si el dump intenta recrear algo que ya existe (p. ej.
# una extensión) pg_restore lo informa y sigue; los conteos del paso 4 son el
# control real. --no-owner deja todo a nombre de quien restaura.
pg_restore -d "$RESTORED" --no-owner --role="$PGUSER" "$DUMP" 2>"${BACKUP_DIR}/restore.log" || true
if [ -s "${BACKUP_DIR}/restore.log" ]; then
    echo "Mensajes de pg_restore (primeras líneas; revisalos, no siempre son graves):"
    sed -n '1,6p' "${BACKUP_DIR}/restore.log"
else
    echo "pg_restore terminó sin mensajes de error."
fi
psql_db "$RESTORED" -c "SELECT timescaledb_post_restore()"

echo
echo "=== 4. Comparación de filas por tabla (como dueño, sin RLS) ==="
echo "Qué observar: las dos columnas coinciden en todas las tablas, incluida la hipertabla measurements."
psql_db "$DB" -Atc "$COUNTS_SQL" >"${BACKUP_DIR}/counts_original.txt"
psql_db "$RESTORED" -Atc "$COUNTS_SQL" >"${BACKUP_DIR}/counts_restored.txt"
printf '%-18s %10s %10s\n' tabla original restaurada
paste -d'|' "${BACKUP_DIR}/counts_original.txt" "${BACKUP_DIR}/counts_restored.txt" |
    awk -F'|' '{ printf "%-18s %10s %10s\n", $1, $2, $4 }'
if cmp -s "${BACKUP_DIR}/counts_original.txt" "${BACKUP_DIR}/counts_restored.txt"; then
    echo "OK: los conteos coinciden."
else
    echo "ERROR: los conteos difieren." >&2
    exit 1
fi
echo "Políticas RLS restauradas (deben ser 6):"
psql_db "$RESTORED" -Atc "SELECT count(*) FROM pg_policies WHERE policyname = 'tenant_isolation'"

echo
echo "=== 5. Los roles NO viajan en el dump ==="
echo "Qué observar: los roles viven a nivel de CLÚSTER. pg_dump no los incluye (sólo GRANT/OWNER"
echo "que los nombran): en un servidor nuevo hay que crearlos antes (pg_dumpall --roles-only)."
printf 'CREATE ROLE dentro del dump de la base:   '
pg_restore -l "$DUMP" | grep -c 'ROLE' || true
printf 'CREATE ROLE en el respaldo de roles (pg_dumpall --roles-only): '
pg_dumpall --roles-only | grep -c 'CREATE ROLE'

echo
echo "Fin. Para el escenario de error humano: 04-error-humano.sql y luego este script con 'recuperar'."
