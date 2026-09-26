#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
CANONICAL_KEY='iot:last-known:AIR-002'
PRACTICE_KEY='iot:last-known:AIR-002:practice'

compose() {
  docker compose --env-file "$ROOT/.env" -f "$ROOT/compose.yaml" "$@"
}

redis_cli() {
  # REDISCLI_AUTH evita exponer la contraseña como argumento o en la salida.
  compose exec -T redis sh -c \
    'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli --raw "$@"' sh "$@"
}

echo 'Estado derivado de PostgreSQL (copia temporal, no fuente de verdad):'
redis_cli GET "$CANONICAL_KEY"
echo 'TTL restante del estado canónico:'
redis_cli TTL "$CANONICAL_KEY"

echo 'Variación segura sobre una clave descartable con TTL de 20 segundos:'
redis_cli SET "$PRACTICE_KEY" \
  '{"device_id":"AIR-002","practice_note":"variación temporal"}' EX 20
redis_cli GET "$PRACTICE_KEY"
redis_cli TTL "$PRACTICE_KEY"

echo 'Recuperación: se elimina sólo la clave de práctica.'
redis_cli DEL "$PRACTICE_KEY"
echo 'Para reconstruir el estado canónico desde el historial real ejecutá:'
echo "docker compose --env-file $ROOT/.env -f $ROOT/compose.yaml run --rm loader"
