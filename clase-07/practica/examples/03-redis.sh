#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
# Cada organización tiene su namespace: iot:org-<organization_id>:...
CANONICAL_KEY='iot:org-1:last-known:AIR-002'
OTHER_ORG_KEY='iot:org-2:last-known:PLT-001'
PRACTICE_KEY='iot:org-1:last-known:AIR-002:practice'
# Credencial fija de la demo local (ver compose.yaml); no reutilizar en producción.
TENANT1_USER='tenant_1'
TENANT1_PASSWORD='ceiot_redis_tenant1_local_only'

compose() {
  docker compose --env-file "$ROOT/.env" -f "$ROOT/compose.yaml" "$@"
}

# Funciona desde el host (vía docker compose) o dentro del contenedor de Redis
# (`docker compose exec redis sh /lab/examples/03-redis.sh`), donde no hay docker.
redis_cli() {
  # REDISCLI_AUTH evita exponer la contraseña como argumento o en la salida.
  if command -v docker >/dev/null 2>&1; then
    compose exec -T redis sh -c \
      'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli --raw "$@"' sh "$@"
  else
    REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli --raw "$@"
  fi
}

# Igual que redis_cli, pero autenticado como el usuario ACL de una organización.
redis_cli_as() {
  user=$1
  password=$2
  shift 2
  if command -v docker >/dev/null 2>&1; then
    compose exec -T -e REDISCLI_AUTH="$password" redis \
      redis-cli --user "$user" --raw "$@"
  else
    REDISCLI_AUTH="$password" redis-cli --user "$user" --raw "$@"
  fi
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

echo
echo 'Aislamiento por organización (ACL de Redis):'
echo "tenant_1 lee una clave de su namespace (iot:org-1:*): permitido."
redis_cli_as "$TENANT1_USER" "$TENANT1_PASSWORD" GET "$CANONICAL_KEY"
echo "tenant_1 intenta leer la clave de la organización 2: se espera NOPERM."
redis_cli_as "$TENANT1_USER" "$TENANT1_PASSWORD" GET "$OTHER_ORG_KEY" || true
echo "tenant_1 intenta escribir: se espera NOPERM."
redis_cli_as "$TENANT1_USER" "$TENANT1_PASSWORD" SET "$CANONICAL_KEY" pisado || true
echo

echo 'Para reconstruir el estado canónico desde el historial real ejecutá:'
echo 'docker compose --env-file .env -f compose.yaml run --rm loader'
