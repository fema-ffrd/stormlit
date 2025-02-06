#!/bin/bash

# export PGHOST=stormlit-postgis
# export PGUSER=admin
# export PGPASSWORD=password
# export PGDATABASE=postgis

python -m pip install pypgstac[psycopg]

pypgstac migrate --toversion 0.9.2
