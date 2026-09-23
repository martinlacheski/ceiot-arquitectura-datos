#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  printf '%s\n' 'usage: run-redis-example.sh /lab/examples/redis/<example>.redis' >&2
  exit 2
fi

example_file=$1
case "$example_file" in
  /lab/examples/redis/*.redis) ;;
  *)
    printf '%s\n' 'example path must match /lab/examples/redis/*.redis' >&2
    exit 2
    ;;
esac
if [ ! -f "$example_file" ]; then
  printf '%s\n' 'Redis example file does not exist' >&2
  exit 2
fi

case "${REDIS_DATABASE-}" in
  ''|*[!0-9]*)
    printf '%s\n' 'REDIS_DATABASE must be a non-negative integer' >&2
    exit 2
    ;;
esac
case "${REDIS_PRESENCE_TTL_SECONDS-}" in
  ''|*[!0-9]*)
    printf '%s\n' 'REDIS_PRESENCE_TTL_SECONDS must be a positive integer' >&2
    exit 2
    ;;
esac
if [ "$REDIS_PRESENCE_TTL_SECONDS" -le 0 ]; then
  printf '%s\n' 'REDIS_PRESENCE_TTL_SECONDS must be a positive integer' >&2
  exit 2
fi

: "${REDIS_USERNAME:?REDIS_USERNAME is required}"
: "${REDIS_PASSWORD:?REDIS_PASSWORD is required}"
REDISCLI_AUTH=$REDIS_PASSWORD
export REDISCLI_AUTH

sed \
  -e '/^[[:space:]]*$/d' \
  -e '/^[[:space:]]*#/d' \
  -e "s/__PRESENCE_TTL_SECONDS__/$REDIS_PRESENCE_TTL_SECONDS/g" \
  "$example_file" |
  redis-cli --user "$REDIS_USERNAME" -n "$REDIS_DATABASE"
