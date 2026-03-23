from connection import (
    connect_to_catalog,
    ensure_env_variables,
    load_config,
    postgres_connection_string,
    warehouse,
)
from dotenv import load_dotenv

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
            "stormlit_prod_db",
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
    CONFIG_FILE = os.path.join(
        os.getcwd(), "lakehouse/trinity/configs/datalake.config.json"
    )
    load_dotenv()
    ensure_env_variables()
    config = load_config(CONFIG_FILE)
    new_table_name_space = "stac"
    main(config, new_table_name_space)
