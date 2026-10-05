#!/bin/sh
# Failover manual (slide 58) y vuelta al estado inicial.
#
#   sh examples/07-failover.sh          # cae el primario y se promueve la réplica
#   sh examples/07-failover.sh reset    # deja todo como antes: primario + réplica en streaming
#
# DESTRUCTIVO PARA LA RÉPLICA: tras la promoción deja de ser réplica y `reset`
# borra su volumen (postgres_replica_data) para clonarla de nuevo desde el
# primario. El volumen de datos del primario NUNCA se toca: el primario
# sólo se detiene y se vuelve a iniciar.
#
# Lección: la aplicación sigue apuntando al servicio "postgres". Nadie la
# redirige a la réplica promovida; eso requiere una herramienta de orquestación
# (Patroni, repmgr, un balanceador con health checks...).
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PROJECT=ceiot-clase-07

compose() {
  docker compose --env-file "$ROOT/.env" -f "$ROOT/compose.yaml" --profile replica "$@"
}

replica_sql() { compose exec -T postgres-replica sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"' sh "$@"; }

if [ "${1:-}" = "reset" ]; then
  echo "=== Reset: de vuelta a primario + réplica en streaming ==="
  compose stop postgres-replica
  compose rm -f postgres-replica
  # Sólo el volumen de la réplica; el del primario no se toca.
  docker volume rm "${PROJECT}_postgres_replica_data" >/dev/null 2>&1 || true
  compose start postgres
  # El slot replica_1 quedó huérfano en el primario (inactivo): se elimina.
  # (El entrypoint de la réplica también lo hace si hiciera falta.)
  i=0
  until compose exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
    i=$((i + 1)); [ "$i" -lt 60 ] || { echo "El primario no arrancó" >&2; exit 1; }
    sleep 1
  done
  compose exec -T postgres sh -c 'psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
    "SELECT pg_drop_replication_slot(slot_name) FROM pg_replication_slots WHERE slot_name = '"'"'replica_1'"'"' AND NOT active"'
  compose up -d --wait postgres postgres-replica
  compose exec -T postgres sh -c 'psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
    "SELECT application_name, state, replay_lsn FROM pg_stat_replication"'
  echo "Réplica otra vez en streaming."
  exit 0
fi

echo "=== 1. Estado inicial ==="
replica_sql -Atc "SELECT 'réplica en recuperación: ' || pg_is_in_recovery()"

echo
echo "=== 2. Cae el primario ==="
compose stop postgres
echo "La aplicación (servicio app) sigue apuntando a 'postgres', que ya no responde:"
echo "no hay failover automático. Hay que decidir y actuar."

echo
echo "=== 3. Promover la réplica: pg_promote() ==="
echo "Qué observar: pg_is_in_recovery() pasa de t a f y el INSERT, que antes fallaba, ahora funciona."
replica_sql -c "SELECT pg_promote(wait => true)"
replica_sql -c "SELECT pg_is_in_recovery() AS en_recuperacion"
replica_sql -c "INSERT INTO measurements (organization_id, device_id, measured_at, variable, value, unit, quality)
                VALUES (1, 'AIR-002', now(), 'failover_demo', 1, 'x', 'GOOD')"
replica_sql -Atc "SELECT 'INSERT en la réplica promovida: ' || count(*) || ' fila' FROM measurements WHERE variable = 'failover_demo'"

echo
echo "Estado actual: el primario original está detenido y la réplica promovida es la nueva fuente de verdad."
echo "Para volver al estado inicial (descarta la réplica promovida y la clona de nuevo):"
echo "  sh examples/07-failover.sh reset"
