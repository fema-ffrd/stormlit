import os
import logging

import duckdb
import pandas as pd
from dotenv import load_dotenv
import streamlit as st

logging.basicConfig(level=logging.INFO)


def get_duckdb_connection():
    """Initialize DuckDB with necessary extensions and S3/Postgres configuration."""
    load_dotenv()

    S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID")
    S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY")
    S3_REGION = os.getenv("S3_REGION")
    POSTGRES_DB = os.getenv("POSTGRES_DB")
    POSTGRES_USER = os.getenv("POSTGRES_USER")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT")

    con = duckdb.connect(database=":memory:")

    # Install & load extensions
    con.execute("INSTALL httpfs;")
    con.execute("LOAD httpfs;")
    con.execute("INSTALL iceberg;")
    con.execute("LOAD iceberg;")
    con.execute("INSTALL postgres_scanner;")
    con.execute("LOAD postgres_scanner;")

    # Configure S3
    con.execute(f"SET s3_access_key_id='{S3_ACCESS_KEY_ID}';")
    con.execute(f"SET s3_secret_access_key='{S3_SECRET_ACCESS_KEY}';")
    con.execute(f"SET s3_region='{S3_REGION}';")
    con.execute("SET s3_url_style='path';")
    con.execute("SET s3_use_ssl='true';")

    # Postgres connection string
    pg_str = f"dbname={POSTGRES_DB} user={POSTGRES_USER} password={POSTGRES_PASSWORD} host={POSTGRES_HOST} port={POSTGRES_PORT}"

    return con, pg_str


def get_iceberg_metadata(con, pg_str, target_bucket: str, table_name="storms"):
    """Get Iceberg table metadata from the Postgres catalog."""
    try:
        catalogs = con.sql(
            f"""
            SELECT *
            FROM postgres_scan(
                '{pg_str}',
                'pgstac',
                'iceberg_tables'
            )
            WHERE table_name = '{table_name}'
            LIMIT 20;
        """
        ).df()
        if not catalogs.empty:
            metadata_location = catalogs["metadata_location"].iloc[0]
            bucket = metadata_location.split("/")[2]
            if bucket == target_bucket:
                return catalogs
            else:
                logging.warning(
                    f"Metadata location bucket {bucket} does not match target bucket {target_bucket}"
                )
                return None
    except Exception as e:
        logging.error(f"Error fetching Iceberg metadata: {e}")
        return None


def query_storms(
    con,
    metadata_location: str,
    limit: int,
    order_by_name: str = "id",
    order_by: str = "ASC",
):
    """Query and list all storms from the STAC items Iceberg table using metadata location."""
    try:
        order_by_key = order_by_name.lower().strip()
        order_by_direction = order_by.upper().strip()
        if order_by_direction not in {"ASC", "DESC"}:
            order_by_direction = "ASC"

        # Map user-facing column names to safe SQL expressions.
        order_by_expr_map = {
            "id": "CAST(id AS INTEGER)",
            "rank": "CAST(id AS INTEGER)",
            "collection": "collection",
            "storm_type": "storm_type",
            "datetime": "CAST(datetime AS TIMESTAMP)",
        }
        order_by_expr = order_by_expr_map.get(order_by_key, "CAST(id AS INTEGER)")

        # Query the Iceberg table using the metadata location
        result = con.sql(
            f"""
            SELECT 
                CAST(id AS INTEGER) as rank,
                collection,
                storm_type,
                CAST(datetime AS TIMESTAMP) as datetime,
                assets
            FROM iceberg_scan('{metadata_location}')
            ORDER BY {order_by_expr} {order_by_direction}
            LIMIT {limit};
        """
        ).df()

        return result

    except Exception as e:
        logging.error(f"Error querying storms: {e}")

        # If no snapshots, try reading the metadata JSON directly
        logging.info(
            f"Attempting alternative approach with metadata location: {metadata_location}"
        )
        try:
            metadata_content = con.sql(
                f"""
                SELECT * FROM read_json_auto('{metadata_location}')
                LIMIT {limit};
            """
            ).df()
            logging.info(f"Metadata structure:\n{metadata_content}")
            return None
        except Exception as e2:
            logging.error(f"Alternative approach also failed: {e2}")
            return None


def query_storms_with_assets(
    con, metadata_location, limit: int, order_by_name: str = "id", order_by: str = "ASC"
):
    """Query storms and extract asset hrefs, returning a list of storm records."""
    import json

    try:
        # Get the base query results
        storms_df = query_storms(
            con,
            metadata_location,
            limit=limit,
            order_by_name=order_by_name,
            order_by=order_by,
        )

        if storms_df is None or len(storms_df) == 0:
            return []

        # Process results and extract asset hrefs
        storms_list = []
        for _, row in storms_df.iterrows():
            storm_rank = row["rank"]
            collection = row["collection"]
            storm_type = row["storm_type"]
            datetime = row["datetime"]
            assets_str = row["assets"]

            # Try to parse assets as JSON string
            aorc_storm_href = None
            try:
                # Parse JSON string
                assets_dict = json.loads(assets_str)
                # Extract href from aorc_storm asset
                if "aorc_storm" in assets_dict:
                    aorc_asset = assets_dict["aorc_storm"]
                    if isinstance(aorc_asset, dict) and "href" in aorc_asset:
                        aorc_storm_href = aorc_asset["href"]
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logging.debug(f"Failed to parse assets for {storm_rank}: {e}")

            # Add storm record to list
            storms_list.append(
                {
                    "rank": storm_rank,
                    "collection": collection,
                    "storm_type": storm_type,
                    "datetime": str(datetime),
                    "aorc_storm_href": aorc_storm_href,
                }
            )

        return storms_list

    except Exception as e:
        logging.error(f"Error querying storms with assets: {e}")
        return []


@st.cache_data
def query_iceberg_table(
    table_name: str,
    target_bucket: str,
    num_rows: int,
    order_by_name: str = "rank",
    order_by: str = "ASC",
):
    """Main function to query Iceberg metadata and storms data."""
    con, pg_str = get_duckdb_connection()
    try:
        # Get metadata for the storms table
        metadata = get_iceberg_metadata(con, pg_str, target_bucket, table_name)

        if metadata is not None and len(metadata) > 0:
            metadata_location = metadata.iloc[0]["metadata_location"]
            logging.info(f"Metadata location: {metadata_location}")

            if table_name == "storms":
                # Query storms and extract assets
                items_list = query_storms_with_assets(
                    con,
                    metadata_location,
                    limit=num_rows,
                    order_by_name=order_by_name,
                    order_by=order_by,
                )
            else:
                logging.info(f"Querying for table {table_name} is not implemented yet")
                items_list = []

            if items_list:
                logging.info(
                    f"Retrieved {len(items_list)} items from {table_name} table"
                )
                items_df = pd.DataFrame(items_list or [])
                return items_df
            else:
                logging.info(
                    f"{table_name} table appears to be empty or no items found"
                )
        else:
            logging.info(f"{table_name} table not found in metadata")

    finally:
        con.close()


if __name__ == "__main__":
    query_iceberg_table(
        "storms",
        target_bucket="trinity-pilot",
        num_rows=10,
        order_by_name="rank",
        order_by="ASC",
    )
