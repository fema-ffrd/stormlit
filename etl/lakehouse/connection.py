"""Utility functions for connecting to Iceberg catalog and managing configurations."""

import json
import logging
import os

import yaml
from dotenv import load_dotenv
from pyiceberg.catalog.sql import SqlCatalog

load_dotenv(override=True)


PROJECTS_YAML = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "app", "src", "configs", "projects.yaml")
)


def load_project_config(project_name: str, config_path: str = PROJECTS_YAML) -> dict:
    """Load project configuration from projects.yaml by project name.

    Parameters
    ----------
    project_name : str
        The name of the project to load (case-insensitive match).
    config_path : str
        Path to the projects.yaml file.

    Returns
    -------
    dict
        Dictionary with keys ``catalog_name``, ``warehouse_prefix``, and ``s3_bucket``.
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {config_path}")

    projects = data.get("projects", [])
    for entry in projects:
        if not entry:
            continue
        if entry.get("name", "").lower() == project_name.lower():
            required = ["catalog_name", "warehouse_prefix", "bucket"]
            missing = [k for k in required if not entry.get(k)]
            if missing:
                raise ValueError(
                    f"Project '{project_name}' is missing required keys: {', '.join(missing)}"
                )
            return {
                "catalog_name": entry["catalog_name"],
                "warehouse_prefix": entry["warehouse_prefix"],
                "s3_bucket": entry["bucket"],
            }

    available = [e.get("name", "?") for e in projects if e]
    raise ValueError(
        f"Project '{project_name}' not found in {config_path}. "
        f"Available projects: {available}"
    )


def load_config(config_file: str):
    """Load catalog configuration from JSON file and validate required keys are present."""

    required_keys = ["catalog_name", "warehouse_prefix", "s3_bucket"]

    try:
        with open(config_file, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {config_file}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file {config_file}: {e}")

    missing_keys = [key for key in required_keys if key not in config]

    if missing_keys:
        raise ValueError(
            f"Missing required keys in {config_file}: {', '.join(missing_keys)}"
        )

    return config


def ensure_env_variables(aws_required: bool = True):
    """Validate that all required environment variables are set."""
    required_vars = [
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
    ]

    if aws_required:
        required_vars.extend(["S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_REGION"])

    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        error_msg = (
            f"Missing required environment variables: {', '.join(missing_vars)}. "
            f"Please set these variables before running storm_catalog."
        )
        raise ValueError(error_msg)

    logging.info("All required environment variables are set.")
    return True


def warehouse(s3_bucket: str, warehouse_prefix: str):
    """Get the catalog root from the configuration."""
    return f"s3://{s3_bucket}/{warehouse_prefix}"


def postgres_connection_string(
    postgres_host: str,
    postgres_port: str,
    postgres_user: str,
    postgres_password: str,
    postgres_db: str,
):
    """Generate a PostgreSQL connection string."""
    return (
        f"postgresql+psycopg://{postgres_user}:{postgres_password}"
        f"@{postgres_host}:{postgres_port}/{postgres_db}"
    )


def connect_to_catalog(
    pg_conn_string: str,
    catalog_name: str,
    catalog_root: str,
    s3_access_key_id: str,
    s3_secret_access_key: str,
    s3_region: str,
):
    """Connect to an Iceberg SQL catalog using provided connection parameters.
    Args:
       pg_conn_string (str): PostgreSQL connection string.
       catalog_name (str): Name of the Iceberg catalog.
       catalog_root (str): Root path for the Iceberg catalog in S3.
       s3_access_key_id (str): AWS S3 access key ID.
       s3_secret_access_key (str): AWS S3 secret access key.
       s3_region (str): AWS S3 region.
    Returns:
       SqlCatalog: Connected Iceberg SQL catalog object or None if connection fails.
    """
    try:
        catalog = SqlCatalog(
            catalog_name,
            **{
                "uri": pg_conn_string,
                "icedev": catalog_root,
                "s3.access-key-id": s3_access_key_id,
                "s3.secret-access-key": s3_secret_access_key,
                "s3.path-style-access": "true",
                "s3.region": s3_region,
                "py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO",
            },
        )
        logging.info(f"Connected to Iceberg catalog: `{catalog_name}`")
        return catalog
    except Exception as e:
        logging.error(f"Cannot connect to Iceberg catalog: {e}")
        raise
