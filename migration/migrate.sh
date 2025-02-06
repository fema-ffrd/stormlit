#!/bin/bash

# # Download RDS certificate if it doesn't exist
# if [ ! -f "global-bundle.pem" ]; then
#     curl -o global-bundle.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
# fi

# Database connection settings
# export PGHOST=""
# export PGUSER="stormlit_admin"
# export PGPASSWORD='' # use single quotes to escape special characters
# export PGDATABASE="postgres"
# export PGSSLMODE="require"
# export PGSSLROOTCERT="$(pwd)/global-bundle.pem"

# Install pypgstac with its dependencies
python -m pip install 'pypgstac[psycopg]'

# Run the migration
pypgstac migrate --toversion 0.9.2
