#!/bin/bash

# Download RDS certificate if it doesn't exist
if [ ! -f "global-bundle.pem" ]; then
    curl -o global-bundle.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
fi

# Database connection settings, get secrets from AWS secrets manager
export PGHOST=""
export PGUSER="stormlit_admin"
export PGPASSWORD='' # use single quotes to escape special characters
export PGSTAC_ADMIN_PASSWORD=''
export PGSTAC_INGEST_PASSWORD=''
export PGSTAC_READ_PASSWORD=''
export PGDATABASE="postgres"
export PGSSLMODE="require"
export PGSSLROOTCERT="$(pwd)/global-bundle.pem"

# Install pypgstac with its dependencies
python -m pip install 'pypgstac[psycopg]'

# Run the migration
pypgstac migrate --toversion 0.9.2

# Set passwords for pgstac roles
psql -h $PGHOST -U $PGUSER -d $PGDATABASE -c "ALTER ROLE pgstac_admin LOGIN PASSWORD '${PGSTAC_ADMIN_PASSWORD}';"
psql -h $PGHOST -U $PGUSER -d $PGDATABASE -c "ALTER ROLE pgstac_ingest LOGIN PASSWORD '${PGSTAC_INGEST_PASSWORD}';"
psql -h $PGHOST -U $PGUSER -d $PGDATABASE -c "ALTER ROLE pgstac_read LOGIN PASSWORD '${PGSTAC_READ_PASSWORD}';"
