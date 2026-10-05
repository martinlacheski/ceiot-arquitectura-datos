#!/bin/sh
# Escalabilidad con pgbench (slides 65-68): vertical, horizontal de lectura y sharding.
#
# Se ejecuta desde el HOST:
#
#   sh examples/08-escalabilidad.sh [etiqueta]   # mide y agrega una fila a la tabla de resultados
#   sh examples/08-escalabilidad.sh limpiar      # borra la base bench
#
# Vertical (slides 65-66): la misma prueba con menos CPU. Los pasos:
#   1) sh examples/08-escalabilidad.sh cpus-2        (POSTGRES_CPUS=2, el valor por defecto)
#   2) en .env: POSTGRES_CPUS=1  y  docker compose --env-file .env -f compose.yaml up -d postgres
#      (recrea el contenedor con otro tope; los datos del volumen quedan)
#   3) sh examples/08-escalabilidad.sh cpus-1        y comparar las filas de la tabla final
#   4) volver al valor original y repetir el `up -d postgres`
#
# Horizontal de lectura (slide 67): si la réplica está corriendo
# (docker compose --profile replica up -d --wait) se mide también el -S repartido
# entre primario y réplica. Las escrituras siguen yendo sólo al primario.
#
# La base bench (pgbench -i -s 10, ~150 MB) se crea en el primario si falta; la
# réplica la recibe sola porque la replicación física copia todo el clúster.
# Duración aproximada: 2-3 minutos (cada medición dura 20 s).
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
CLIENTS=8
THREADS=4
SECONDS_PER_RUN=20
RESULTS=/home/postgres/pgdata/backup/escalabilidad.txt

compose() {
  docker compose --env-file "$ROOT/.env" -f "$ROOT/compose.yaml" --profile replica "$@"
}

# Los clientes de pgbench corren dentro de cada contenedor (socket local, sin contraseña).
primary_sh() { compose exec -T postgres sh -c "$1"; }
replica_sh() { compose exec -T postgres-replica sh -c "$1"; }
PGB='pgbench -U "$POSTGRES_USER"'

if [ "${1:-}" = "limpiar" ]; then
  primary_sh 'psql -X -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS bench WITH (FORCE)"'
  exit 0
fi
LABEL="${1:-actual}"

have_replica=no
if compose ps --status running --services | grep -qx postgres-replica; then have_replica=yes; fi

tps_of() { sed -n 's/^tps = \([0-9.]*\).*/\1/p'; }

echo "=== 1. Preparación: base bench ==="
if [ "$(primary_sh 'psql -X -U "$POSTGRES_USER" -d postgres -Atc "SELECT count(*) FROM pg_database WHERE datname = '"'"'bench'"'"'"')" = 0 ]; then
  primary_sh 'psql -X -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE bench"'
fi
if [ "$(primary_sh 'psql -X -U "$POSTGRES_USER" -d bench -Atc "SELECT to_regclass('"'"'pgbench_accounts'"'"') IS NOT NULL"')" != t ]; then
  primary_sh "$PGB"' -i -s 10 -q bench' 2>&1 | tail -2
fi
echo "Tope de CPU del primario (cgroup cpu.max: cuota y período en microsegundos): $(primary_sh 'cat /sys/fs/cgroup/cpu.max')"

echo
echo "=== 2. Sólo el primario: pgbench -S (solo lecturas), $CLIENTS clientes, ${SECONDS_PER_RUN} s ==="
echo "Qué observar: las transacciones por segundo (tps) dependen del CPU asignado."
primary_tps=$(primary_sh "$PGB"' -n -S -c '$CLIENTS' -j '$THREADS' -T '$SECONDS_PER_RUN' bench' | tee /dev/stderr | tps_of)
echo "=> primario solo: $primary_tps tps"

combined=""
if [ "$have_replica" = yes ]; then
  echo
  echo "=== 3. Escala horizontal de lectura: el mismo -S contra primario Y réplica a la vez ==="
  echo "Qué observar: la réplica atiende lecturas con su propio CPU; el total supera al primario solo."
  i=0
  until [ "$(replica_sh 'psql -X -U "$POSTGRES_USER" -d bench -Atc "SELECT to_regclass('"'"'pgbench_accounts'"'"') IS NOT NULL"' 2>/dev/null || true)" = t ]; do
    i=$((i + 1)); [ "$i" -lt 30 ] || { echo "La réplica no recibió la base bench" >&2; exit 1; }
    sleep 1
  done
  tmp=$(mktemp -d)
  primary_sh "$PGB"' -n -S -c '$CLIENTS' -j '$THREADS' -T '$SECONDS_PER_RUN' bench' >"$tmp/p" &
  pid_p=$!
  replica_sh "$PGB"' -n -S -c '$CLIENTS' -j '$THREADS' -T '$SECONDS_PER_RUN' bench' >"$tmp/r" &
  pid_r=$!
  wait "$pid_p" "$pid_r"
  tps_p=$(tps_of <"$tmp/p"); tps_r=$(tps_of <"$tmp/r")
  rm -rf "$tmp"
  combined=$(awk -v a="$tps_p" -v b="$tps_r" 'BEGIN { printf "%.0f", a + b }')
  echo "=> primario: $tps_p tps + réplica: $tps_r tps = $combined tps combinados (sólo primario: $primary_tps)"

  echo
  echo "=== 4. Las escrituras no escalan así: pgbench con TPC-B (escribe) contra la réplica ==="
  echo "Qué observar: falla con 'read-only transaction'. Escribir sigue siendo cosa del primario."
  replica_sh "$PGB"' -n -c 1 -t 1 bench' 2>&1 | sed -n '1,4p' || true
else
  echo
  echo "(Sin réplica: para ver escala horizontal de lectura levantala con"
  echo " docker compose --env-file .env -f compose.yaml --profile replica up -d --wait)"
fi

primary_sh "echo '$LABEL|$(date +%H:%M:%S)|$primary_tps|${combined:--}' >>$RESULTS"
echo
echo "=== Resultados acumulados (etiqueta | hora | tps primario | tps primario+réplica) ==="
primary_sh "cat $RESULTS"

echo
echo "=== Sharding (slide 68) ==="
echo "No se implementa en esta práctica: repartir las filas entre servidores distintos por una clave"
echo "de shard (p. ej. organization_id) es el tema de la clase 8."
