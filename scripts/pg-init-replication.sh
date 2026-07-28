#!/bin/bash
# =============================================================================
# PostgreSQL Primary — Create replication user
# =============================================================================
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'replicator') THEN
            CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD 'replicator_secret';
            GRANT CONNECT ON DATABASE $POSTGRES_DB TO replicator;
        END IF;
    END
    \$\$;
EOSQL

echo "Replication user 'replicator' created successfully."
