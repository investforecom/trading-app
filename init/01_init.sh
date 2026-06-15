#!/bin/bash
# Runs once when the postgres container is first created.
# Creates the 'metabase' database for Metabase's internal app state.
# The 'trading' database and 'trading' user are already created by
# POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD in the container env.
set -e

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" \
     --dbname   "$POSTGRES_DB" \
     <<-EOSQL
    CREATE DATABASE metabase;
    GRANT ALL PRIVILEGES ON DATABASE metabase TO "$POSTGRES_USER";
EOSQL

echo "init: 'metabase' database created and granted to $POSTGRES_USER"
