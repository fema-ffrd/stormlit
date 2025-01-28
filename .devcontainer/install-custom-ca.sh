#! /usr/bin/env bash
set -e

# Custom CA files
custom_ca=$(find /tmp -maxdepth 1 -name "*.crt")
if [ -z "$custom_ca" ]; then
    echo "No custom CA files provided."
    exit 0
fi

# Add custom CA files to /usr/local/share/ca-certificates
cp $custom_ca /usr/local/share/ca-certificates/

update-ca-certificates
