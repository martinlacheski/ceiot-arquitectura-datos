#!/bin/sh
# Réplica de streaming (slides 56-58 y 53): lag y "una réplica no es un backup".
#
# Se ejecuta desde el HOST (necesita docker compose para pausar la réplica):
#
#   docker compose --env-file .env -f compose.yaml --profile replica up -d --wait
#   sh examples/07-replicacion.sh
#
# No destruye nada: las filas de demostración se borran al final y el borrado de
# PLT-002 se recupera desde el respaldo (04-backup-restore.sh). El failover, que
# sí deja la réplica promovida, está aparte en 07-failover.sh.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

compose() {
  docker compose --env-file "$ROOT/.env" -f "$ROOT/compose.yaml" --profile replica "$@"
}

# Los comandos corren dentro de cada contenedor como dueño (confianza por socket local).
primary_sql() { compose exec -T postgres sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"' sh "$@"; }
replica_sql() { compose exec -T postgres-replica sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"' sh "$@"; }

# Espera (hasta ~15 s) a que la consulta de la réplica devuelva el valor esperado.
wait_replica() { # wait_replica <consulta> <valor esperado>
  i=0
  while [ "$i" -lt 30 ]; do
    got=$(replica_sql -Atc "$1")
    [ "$got" = "$2" ] && return 0
    i=$((i + 1))
    sleep 0.5
  done
  echo "La réplica no llegó a '$2' (último valor: '$got')" >&2
  return 1
}

compose ps --status running --services | grep -qx postgres-replica || {
  echo "La réplica no está corriendo. Levantala con:" >&2
  echo "  docker compose --env-file .env -f compose.yaml --profile replica up -d --wait" >&2
  exit 1
}

echo "=== 1. Primario: pg_stat_replication y slots ==="
primary_sql -f /lab/examples/07-replicacion.sql

echo
echo "=== 2. Réplica: modo recuperación, mismos datos, políticas RLS y escritura rechazada ==="
replica_sql -f /lab/examples/07-replicacion-replica.sql

echo
echo "=== 3. Un INSERT en el primario aparece en la réplica ==="
echo "Qué observar: la fila existe en la réplica casi de inmediato (replicación asincrónica, pero rápida)."
primary_sql -c "INSERT INTO measurements (organization_id, device_id, measured_at, variable, value, unit, quality)
                VALUES (1, 'AIR-002', now(), 'replica_demo', 1, 'x', 'GOOD')"
wait_replica "SELECT count(*) FROM measurements WHERE variable = 'replica_demo'" 1
echo "Visible en la réplica: replica_demo = $(replica_sql -Atc "SELECT count(*) FROM measurements WHERE variable = 'replica_demo'") fila"

echo
echo "=== 4. Lag: réplica pausada mientras el primario sigue escribiendo ==="
echo "Qué observar: con la réplica congelada el retraso en bytes crece con cada escritura; al reanudar, vuelve a 0."
compose pause postgres-replica
primary_sql -c "INSERT INTO measurements (organization_id, device_id, measured_at, variable, value, unit, quality)
                SELECT 1, 'AIR-002', now() - (g || ' seconds')::interval, 'replica_demo', g, 'x', 'GOOD'
                FROM generate_series(1, 20000) AS g
                ON CONFLICT DO NOTHING"
primary_sql -c "SELECT application_name, state, pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS lag_bytes, replay_lag
                FROM pg_stat_replication"
compose unpause postgres-replica
wait_replica "SELECT count(*) FROM measurements WHERE variable = 'replica_demo'" \
  "$(primary_sql -Atc "SELECT count(*) FROM measurements WHERE variable = 'replica_demo'")"
primary_sql -c "SELECT application_name, state, pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS lag_bytes
                FROM pg_stat_replication"
echo "La réplica se puso al día con $(replica_sql -Atc "SELECT count(*) FROM measurements WHERE variable = 'replica_demo'") filas."

echo
echo "Se borran las filas de demostración (el DELETE también se replica)."
primary_sql -c "DELETE FROM measurements WHERE variable = 'replica_demo'"

echo
echo "=== 5. Una réplica NO es un backup (slide 53) ==="
echo "Qué observar: el DELETE accidental se replica igual de rápido que cualquier otro cambio."
echo "Sólo el respaldo lógico permite recuperar los datos."
compose exec -T postgres sh /lab/examples/04-backup-restore.sh >/dev/null
echo "Respaldo listo en el volumen postgres_backups."
echo "PLT-002 antes: primario = $(primary_sql -Atc "SELECT count(*) FROM measurements WHERE device_id = 'PLT-002'")," \
  "réplica = $(replica_sql -Atc "SELECT count(*) FROM measurements WHERE device_id = 'PLT-002'")"
primary_sql -c "DELETE FROM measurements WHERE device_id = 'PLT-002'"
wait_replica "SELECT count(*) FROM measurements WHERE device_id = 'PLT-002'" 0
echo "PLT-002 tras el error humano: primario = $(primary_sql -Atc "SELECT count(*) FROM measurements WHERE device_id = 'PLT-002'")," \
  "réplica = $(replica_sql -Atc "SELECT count(*) FROM measurements WHERE device_id = 'PLT-002'") (la réplica también lo perdió)"
echo "Recuperación desde el dump:"
compose exec -T postgres sh /lab/examples/04-backup-restore.sh recuperar
wait_replica "SELECT count(*) FROM measurements WHERE device_id = 'PLT-002'" \
  "$(primary_sql -Atc "SELECT count(*) FROM measurements WHERE device_id = 'PLT-002'")"
echo "PLT-002 recuperado: primario = $(primary_sql -Atc "SELECT count(*) FROM measurements WHERE device_id = 'PLT-002'")," \
  "réplica = $(replica_sql -Atc "SELECT count(*) FROM measurements WHERE device_id = 'PLT-002'")"

echo
echo "Fin. Siguiente (destructivo para la réplica): sh examples/07-failover.sh"
