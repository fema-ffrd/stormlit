#! /usr/bin/env bash
set -e

# Get the path of this script's parent directory
script_dir=$(dirname "$(realpath "$0")")

# Find custom CA files placed in the container
custom_ca=$(find $script_dir -maxdepth 1 -name "*.crt")
if [ -z "$custom_ca" ]; then
    echo "No custom CA files provided."
    exit 0
fi

# Add custom CA files to /usr/local/share/ca-certificates
cp $custom_ca /usr/local/share/ca-certificates/

update-ca-certificates
