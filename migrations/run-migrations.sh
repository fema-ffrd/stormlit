#!/bin/sh
set -e

echo "Running migrations..."

# get PGHOST from RDS_ENDPOINT
PGHOST=$(echo $RDS_ENDPOINT | cut -d: -f1)
# set the environment variable
export PGHOST

# Force TCP connection and verify environment
if [ -z "$PGHOST" ]; then
    echo "Error: PGHOST environment variable is not set"
    exit 1
fi

# Run each migration script in order
for migration in /migrations/*.sql; do
    echo "Running $migration..."
    # Explicitly use host connection
    PGCONNECT_TIMEOUT=15 psql "host=$PGHOST port=$PGPORT dbname=postgres user=$PGUSER password=$PGPASSWORD sslmode=$PGSSLMODE" \
         -v keycloak_password="$KEYCLOAK_PASSWORD" \
         -v streamlit_password="$STREAMLIT_PASSWORD" \
         -f "$migration"
done

echo "Migrations completed successfully"