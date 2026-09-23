#!/bin/sh
set -eu

: "${REDIS_USERNAME:?REDIS_USERNAME is required}"
: "${REDIS_PASSWORD:?REDIS_PASSWORD is required}"
: "${REDIS_DATABASE:?REDIS_DATABASE is required}"
: "${REDIS_PRESENCE_TTL_SECONDS:?REDIS_PRESENCE_TTL_SECONDS is required}"

case "$REDIS_USERNAME" in
  *[!A-Za-z0-9_.-]*|'')
    printf '%s\n' 'REDIS_USERNAME contains unsupported characters' >&2
    exit 2
    ;;
esac
case "$REDIS_DATABASE" in *[!0-9]*|'') exit 2 ;; esac
case "$REDIS_PRESENCE_TTL_SECONDS" in *[!0-9]*|'') exit 2 ;; esac
[ "$REDIS_PRESENCE_TTL_SECONDS" -gt 0 ] || exit 2

REDISCLI_AUTH=$REDIS_PASSWORD
export REDISCLI_AUTH
redis-cli -h redis -p 6379 --user "$REDIS_USERNAME" -n "$REDIS_DATABASE" \
  --eval /lab/database/01-schema.lua
redis-cli -h redis -p 6379 --user "$REDIS_USERNAME" -n "$REDIS_DATABASE" \
  --eval /lab/database/02-seed.lua , "$REDIS_PRESENCE_TTL_SECONDS"
