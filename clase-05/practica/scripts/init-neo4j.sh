#!/bin/sh
set -eu

: "${NEO4J_USERNAME:?NEO4J_USERNAME is required}"
: "${NEO4J_PASSWORD:?NEO4J_PASSWORD is required}"
: "${NEO4J_DATABASE:?NEO4J_DATABASE is required}"

case "$NEO4J_USERNAME" in
  [A-Za-z]*[!A-Za-z0-9_.-]*|[!A-Za-z]*|'')
    printf '%s\n' 'NEO4J_USERNAME contains unsupported characters' >&2
    exit 2
    ;;
esac
case "$NEO4J_DATABASE" in
  [A-Za-z]*[!A-Za-z0-9_.-]*|[!A-Za-z]*|'')
    printf '%s\n' 'NEO4J_DATABASE contains unsupported characters' >&2
    exit 2
    ;;
esac

cypher-shell -a bolt://neo4j:7687 -u "$NEO4J_USERNAME" \
  -p "$NEO4J_PASSWORD" -d "$NEO4J_DATABASE" \
  -f /lab/database/01-schema.cypher
cypher-shell -a bolt://neo4j:7687 -u "$NEO4J_USERNAME" \
  -p "$NEO4J_PASSWORD" -d "$NEO4J_DATABASE" \
  -f /lab/database/02-seed.cypher
