#!/bin/sh
set -eu

: "${LAB_CASSANDRA_KEYSPACE:?LAB_CASSANDRA_KEYSPACE is required}"
: "${CASSANDRA_REPLICATION_FACTOR:?CASSANDRA_REPLICATION_FACTOR is required}"

case "$LAB_CASSANDRA_KEYSPACE" in
  [A-Za-z]*[!A-Za-z0-9_]*|[!A-Za-z]*|'')
    printf '%s\n' 'LAB_CASSANDRA_KEYSPACE must be an unquoted CQL identifier' >&2
    exit 2
    ;;
esac
case "$CASSANDRA_REPLICATION_FACTOR" in *[!0-9]*|'') exit 2 ;; esac
[ "$CASSANDRA_REPLICATION_FACTOR" -gt 0 ] || exit 2

schema_file=/tmp/clase-05-schema.cql
seed_file=/tmp/clase-05-seed.cql
sed \
  -e "s/__KEYSPACE__/$LAB_CASSANDRA_KEYSPACE/g" \
  -e "s/__REPLICATION_FACTOR__/$CASSANDRA_REPLICATION_FACTOR/g" \
  /lab/database/01-schema.cql > "$schema_file"
sed "s/__KEYSPACE__/$LAB_CASSANDRA_KEYSPACE/g" \
  /lab/database/02-seed.cql > "$seed_file"

cqlsh cassandra 9042 -f "$schema_file"
cqlsh cassandra 9042 -f "$seed_file"
