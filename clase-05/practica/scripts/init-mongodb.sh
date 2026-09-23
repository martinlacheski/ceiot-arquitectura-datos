#!/bin/sh
set -eu

: "${MONGO_DATABASE:?MONGO_DATABASE is required}"
: "${MONGO_ROOT_USERNAME:?MONGO_ROOT_USERNAME is required}"
: "${MONGO_ROOT_PASSWORD:?MONGO_ROOT_PASSWORD is required}"

case "$MONGO_DATABASE" in
  *[!A-Za-z0-9_-]*|'')
    printf '%s\n' 'MONGO_DATABASE contains unsupported characters' >&2
    exit 2
    ;;
esac

mongosh --quiet --host mongo --port 27017 \
  --username "$MONGO_ROOT_USERNAME" \
  --password "$MONGO_ROOT_PASSWORD" \
  --authenticationDatabase admin \
  --file /lab/database/01-schema.js
mongosh --quiet --host mongo --port 27017 \
  --username "$MONGO_ROOT_USERNAME" \
  --password "$MONGO_ROOT_PASSWORD" \
  --authenticationDatabase admin \
  --file /lab/database/02-seed.js
