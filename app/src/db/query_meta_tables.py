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
    con.execute(f"""
        CREATE OR REPLACE SECRET aws_secret (
            TYPE s3,
            PROVIDER credential_chain,
            REGION '{S3_REGION}'
        )
    """)
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
):
    """Query and list all storms from the STAC items Iceberg table using metadata location."""
    try:
        # Query the Iceberg table using the metadata location
        result = con.sql(
            f"""
            SELECT *
            FROM iceberg_scan('{metadata_location}')
            ORDER BY CAST(id AS INTEGER) ASC
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
    con, metadata_location, limit: int
):
    """Query storms and extract asset hrefs, returning a list of storm records."""
    import json

    try:
        # Get the base query results
        storms_df = query_storms(
            con,
            metadata_location,
            limit=limit,
        )

        if storms_df is None or len(storms_df) == 0:
            return []

        # Process results and extract asset hrefs
        storms_list = []
        for _, row in storms_df.iterrows():
            if "id" in row:
                storm_rank = row["id"]
            else:
                storm_rank = None
            if "collection" in row:
                collection = row["collection"]
            else:
                collection = None
            if "storm_type" in row:
                storm_type = row["storm_type"]
            else:
                storm_type = None
            if "datetime" in row:
                datetime = row["datetime"]
            else:
                datetime = None
            if "assets" in row:
                assets_str = row["assets"]
            else:
                assets_str = None

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
        table_name="storms",
        target_bucket="trinity-pilot",
        num_rows=10,
    )
