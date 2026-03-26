from connection import (
    connect_to_catalog,
    ensure_env_variables,
    load_project_config,
    postgres_connection_string,
    warehouse,
)
from dotenv import load_dotenv

import argparse
import logging
import os

logging.basicConfig(level=logging.INFO)


def main(config: dict, table_name_space: str):
    # # Catalog info From Config
    catalog_name = config.get("catalog_name")
    warehouse_prefix = config.get("warehouse_prefix")
    s3_bucket = config.get("s3_bucket")

    catalog_root = warehouse(s3_bucket, warehouse_prefix)
    print(f"Catalog Root: {catalog_root}")

    catalog = connect_to_catalog(
        pg_conn_string=postgres_connection_string(
            os.getenv("POSTGRES_HOST"),
            os.getenv("POSTGRES_PORT"),
            os.getenv("POSTGRES_USER"),
            os.getenv("POSTGRES_PASSWORD"),
            os.getenv("POSTGRES_DB"),
        ),
        catalog_name=catalog_name,
        catalog_root=catalog_root,
        s3_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
        s3_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
        s3_region=os.getenv("S3_REGION"),
    )

    name_spaces = [ns[0] for ns in catalog.list_namespaces()]
    print(f"Existing namespaces: {name_spaces}")

    name_spaces = [ns[0] for ns in catalog.list_namespaces()]
    if table_name_space not in name_spaces:
        catalog.create_namespace(table_name_space)
        print(f"Created namespace: {table_name_space}")
    else:
        print(f"Namespace already exists: {table_name_space}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create an Iceberg table namespace.")
    parser.add_argument(
        "--project",
        required=True,
        help="Project name from projects.yaml (e.g. Trinity)",
    )
    parser.add_argument(
        "--config", default=None, help="Path to projects.yaml (default: auto-resolved)"
    )
    parser.add_argument(
        "--namespace", default="stac", help="Table namespace to create (default: stac)"
    )
    args = parser.parse_args()

    load_dotenv(override=True)
    ensure_env_variables()
    kwargs = {"project_name": args.project}
    if args.config:
        kwargs["config_path"] = args.config
    config = load_project_config(**kwargs)
    main(config, args.namespace)
