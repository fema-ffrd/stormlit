import json
import os
import logging

import duckdb
import geopandas as gpd
import pandas as pd
import shapely.wkb
from dotenv import load_dotenv
import streamlit as st

logging.basicConfig(level=logging.INFO)


def get_duckdb_connection(aws_region: str = "us-east-1"):
    """Initialize DuckDB with necessary extensions and S3/Postgres configuration."""
    load_dotenv()
    POSTGRES_DB = "stormlit_prod_db"
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
            REGION '{aws_region}'
        )
    """)
    con.execute("SET s3_url_style='path';")
    con.execute("SET s3_use_ssl='true';")

    # Postgres connection string
    pg_str = f"dbname={POSTGRES_DB} user={POSTGRES_USER} password={POSTGRES_PASSWORD} host={POSTGRES_HOST} port={POSTGRES_PORT}"

    return con, pg_str


def get_iceberg_metadata(
    con,
    pg_str,
    target_bucket: str,
    table_name: str = "storms",
    catalog_name: str = "stormlit_dev",
    table_namespace: str = "stac",
    check_bucket: bool = True,
):
    """Get Iceberg table metadata from the Postgres catalog.

    Parameters
    ----------
    check_bucket : bool
        When True (default) the ``metadata_location`` S3 bucket is verified
        against ``target_bucket``.  Pass ``False`` for shared tables (e.g.
        ``model_source_data``) whose data live in the catalog-owner bucket
        regardless of which pilot is being queried.
    """
    try:  # iceberg_tables
        catalogs = con.sql(
            f"""
            SELECT *
            FROM postgres_scan(
                '{pg_str}',
                'public',
                'iceberg_tables'
            )
            WHERE catalog_name = '{catalog_name}'
              AND table_namespace = '{table_namespace}'
              AND table_name = '{table_name}'
        """
        ).df()
        if not catalogs.empty:
            if not check_bucket:
                return catalogs
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


def query_storms_with_assets(con, metadata_location, limit: int):
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
        # else:
        #     return storms_df.to_dict(orient="records")

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
            if "aorc:statistics" in row:
                aorc_stats_str = row["aorc:statistics"]
            if "aorc:transform" in row:
                aorc_transform_str = row["aorc:transform"]
            else:
                assets_str = None
                aorc_stats_str = None
                aorc_transform_str = None

            # Try to parse assets as JSON string
            aorc_storm_href = None
            try:
                # Parse JSON string
                assets_dict = json.loads(assets_str)
                aorc_stats_str = json.loads(aorc_stats_str) if aorc_stats_str else None
                aorc_transform_str = (
                    json.loads(aorc_transform_str) if aorc_transform_str else None
                )
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
                    "aorc_statistics": aorc_stats_str,
                    "aorc_transform": aorc_transform_str,
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
        metadata = get_iceberg_metadata(
            con,
            pg_str,
            target_bucket,
            table_name,
            catalog_name="stormlit_dev",
            table_namespace="stac",
        )

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


@st.cache_data
def query_model_source_layer(
    layer_name: str,
    target_bucket: str,
    catalog_name: str = "stormlit_dev",
) -> gpd.GeoDataFrame:
    """
    Query rows from the ``model_source_data`` Iceberg table that match a given
    layer name, and return them as a GeoDataFrame.

    Parameters
    ----------
    layer_name : str
        Value of the ``layer`` field inside the ``metadata`` JSON column
        (e.g. ``'Study Area'`` or ``'Transposition Domain'``).
    target_bucket : str
        S3 bucket that owns the Iceberg catalog (e.g. ``'trinity-pilot'``).
    catalog_name : str
        PyIceberg catalog name registered in the Postgres catalog table.
    """
    _EMPTY = gpd.GeoDataFrame(
        columns=[
            "data_id",
            "data",
            "metadata",
            "assets",
            "lat",
            "lon",
            "layer",
            "geometry",
        ],
        geometry="geometry",
        crs="EPSG:4326",
    )

    con, pg_str = get_duckdb_connection()
    try:
        metadata = get_iceberg_metadata(
            con,
            pg_str,
            target_bucket,
            table_name="model_source_data",
            catalog_name=catalog_name,
            table_namespace="stac",
            check_bucket=False,
        )
        if metadata is None or metadata.empty:
            logging.error("model_source_data not found for bucket '%s'", target_bucket)
            return _EMPTY

        metadata_location = metadata.iloc[0]["metadata_location"]
        df = con.sql(
            f"SELECT data_id, data, metadata, assets, geometry "
            f"FROM iceberg_scan('{metadata_location}')"
        ).df()
    finally:
        con.close()

    if df.empty:
        logging.warning("model_source_data is empty for bucket '%s'", target_bucket)
        return _EMPTY

    # Filter to the requested layer in Python to avoid DuckDB JSON dialect issues
    def _layer(meta_str):
        try:
            return json.loads(meta_str or "{}").get("layer", "")
        except (json.JSONDecodeError, TypeError):
            return ""

    # Capture available layer names before filtering, for diagnostics
    all_layers = sorted(df["metadata"].apply(_layer).unique().tolist())
    df = df[df["metadata"].apply(_layer) == layer_name]

    if df.empty:
        logging.warning(
            "No rows found for layer '%s'. Available layers in model_source_data: %s. "
            "Run load_geojson_to_iceberg.py with --layer-name '%s' to populate this layer.",
            layer_name,
            all_layers,
            layer_name,
        )
        return _EMPTY

    def _load_wkb(val):
        """Convert a DuckDB binary value (bytes/bytearray/memoryview) to a Shapely geometry."""
        if val is None:
            return None
        raw = val.tobytes() if isinstance(val, memoryview) else bytes(val)
        try:
            return shapely.wkb.loads(raw)
        except Exception:
            try:
                return shapely.wkb.loads(raw, hex=True)
            except Exception as exc:
                logging.warning("Failed to load WKB geometry: %s", exc)
                return None

    rows = []
    for _, row in df.iterrows():
        props = json.loads(row["data"]) if row["data"] else {}
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        rows.append(
            {
                "data_id": row["data_id"],
                **props,
                "lat": meta.get("lat"),
                "lon": meta.get("lon"),
                "layer": layer_name,
                "geometry": _load_wkb(row["geometry"]),
            }
        )

    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    gdf = gdf.set_geometry("geometry")
    return gdf


def query_study_area(
    target_bucket: str,
    catalog_name: str = "stormlit_dev",
    layer_prefix: str | None = None,
) -> gpd.GeoDataFrame:
    """Return the Study Area layer from the model_source_data Iceberg table."""
    prefix = layer_prefix if layer_prefix else target_bucket.replace("-", "_")
    layer_name = f"{prefix}_study_area"
    return query_model_source_layer(layer_name, target_bucket, catalog_name)


def query_transpo_domain(
    target_bucket: str,
    catalog_name: str = "stormlit_dev",
    layer_prefix: str | None = None,
) -> gpd.GeoDataFrame:
    """Return the Transposition Domain layer from the model_source_data Iceberg table."""
    prefix = layer_prefix if layer_prefix else target_bucket.replace("-", "_")
    layer_name = f"{prefix}_transpo_domain"
    return query_model_source_layer(layer_name, target_bucket, catalog_name)


if __name__ == "__main__":
    query_iceberg_table(
        table_name="storms",
        target_bucket="trinity-pilot",
        num_rows=10,
    )
