import pandas as pd
import geopandas as gpd
import streamlit as st
import shapely.wkb
import duckdb
from PIL import Image
import s3fs
from io import BytesIO
import logging

logger = logging.getLogger(__name__)


class StormlitQueryException(Exception):
    pass


def format_to_gdf(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """
    Convert a pandas DataFrame to a GeoDataFrame with EPSG:4326 CRS.

    Parameters:
        df (DataFrame): A pandas DataFrame containing geometry in WKB format.

    Returns:
        gdf (GeoDataFrame): A GeoDataFrame with the geometry column converted to GeoSeries and CRS set to EPSG:4326.
    """
    if "start_datetime" in df.columns:
        # Convert start_datetime and end_datetime to datetime
        df["start_datetime"] = pd.to_datetime(df["start_datetime"])
    if "end_datetime" in df.columns:
        df["end_datetime"] = pd.to_datetime(df["end_datetime"])

    # Convert geometry from WKB to GeoSeries
    def wkb_to_geom(x):
        if isinstance(x, (bytes, bytearray)):
            return shapely.wkb.loads(bytes(x))
        elif isinstance(x, str):
            return shapely.wkb.loads(bytes.fromhex(x))
        else:
            return None

    # Convert geometry from WKB to GeoSeries
    df["geometry"] = df["geometry"].apply(wkb_to_geom)
    gdf = gpd.GeoDataFrame(df, geometry="geometry")
    # Set the CRS to EPSG:4326
    gdf.set_crs(epsg=4326, inplace=True)
    # Convert the geometry to EPSG:4326
    gdf = gdf.to_crs(epsg=4326)
    # Find the center of the map data
    centroids = gdf.geometry.centroid
    gdf["lat"] = centroids.y.astype(float)
    gdf["lon"] = centroids.x.astype(float)
    return gdf


def query_db(_conn, query: str, pg_args: list = None, layer: str = None) -> pd.DataFrame | gpd.GeoDataFrame:
    """
    Execute a SQL query and return the result as a pandas DataFrame.

    Parameters:
        _conn (connection): A DuckDB connection object.
        query (str): The SQL query to execute.
        pg_args (list): Additional arguments for the PostgreSQL query. Default is None.
                        Example: [dsn, schema_name, table_name] for postgres_scan.
        layer (str): Feature layer to assign as a column in the GeoDataFrame.
                    Example: "Reference Lines", "Reference Points", "BC Lines", etc.

    Returns:
        df (DataFrame): A pandas DataFrame or geopandas GeoDataFrame containing
                        the rows returned from the query.
    """
    try:
        # NOTE: A /UTC error occurs when using fetchdf() with duckdb
        df = _conn.execute(query, pg_args).fetchnumpy()
    except duckdb.Error as e:
        msg = f"DuckDB S3 Error: {e}"
        logger.error(msg)
        raise StormlitQueryException(msg) from e

    # Convert the numpy array to a pandas DataFrame
    df = pd.DataFrame(df)
    # Standardize column names
    if "datetime" in df.columns:
        # Convert datetime column to pandas datetime
        df["datetime"] = pd.to_datetime(df["datetime"])
        # rename the datetime column to 'time'
        df.rename(columns={"datetime": "time"}, inplace=True)
    if "time" in df.columns:
        # Convert time column to pandas datetime
        df["time"] = pd.to_datetime(df["time"])
    if "geometry" in df.columns:
        # Convert the DataFrame to a GeoDataFrame
        df = format_to_gdf(df)
    if "refln_name" in df.columns:
        # Convert ref_id to id
        df.rename(columns={"refln_name": "id"}, inplace=True)
    if "refpt_name" in df.columns:
        # Convert ref_id to id
        df.rename(columns={"refpt_name": "id"}, inplace=True)
    if "name" in df.columns:
        # Convert ref_id to id
        df.rename(columns={"name": "id"}, inplace=True)
    if "ref_line" in df.columns:
        # Convert ref_line to ref_id
        df.rename(columns={"ref_line": "id"}, inplace=True)
    if "ref_point" in df.columns:
        # Convert ref_point to ref_id
        df.rename(columns={"ref_point": "id"}, inplace=True)
    if "bc_line" in df.columns:
        # Convert bc_line to ref_id
        df.rename(columns={"bc_line": "id"}, inplace=True)
    if layer is not None:
        # Add a layer column to the DataFrame
        df["layer"] = layer
    return df


@st.cache_data
def query_pg_table_all(
    _conn, dsn: str, schema_name: str, table_name: str
) -> pd.DataFrame | gpd.GeoDataFrame:
    """
    Query all rows from a Postgres table using DuckDB.

    Parameters:
        _conn (connection): A DuckDB connection object.
        dsn (str): The DSN credentials for the PostgreSQL database.
        schema_name (str): The name of the schema where the table is located.
        table_name (str): The name of the table to query.

    Returns:
        pd.DataFrame: A pandas DataFrame containing the rows returned from the query.
    """
    pg_args = [dsn, schema_name, table_name]
    query = "SELECT * FROM postgres_scan(?, ?, ?)"
    return query_db(_conn, query, pg_args=pg_args)


@st.cache_data
def query_pg_table_filter(
    _conn, dsn: str, schema_name: str, table_name: str, col_name: str, search_id: str
) -> pd.DataFrame | gpd.GeoDataFrame:
    """
    Query rows from a Postgres table using DuckDB using a column filter.

    Parameters:
        _conn (connection): A DuckDB connection object.
        dsn (str): The DSN credentials for the PostgreSQL database.
        schema_name (str): The name of the schema where the table is located.
        table_name (str): The name of the table to query.
        col_name (str): The name of the column to filter the query.
        search_id (str): The ID within the column to filter the query to.
    Returns:
        pd.DataFrame: A pandas DataFrame containing the rows returned from the query.
    """
    pg_args = [dsn, schema_name, table_name, search_id]
    query = f"SELECT * FROM postgres_scan(?, ?, ?) WHERE {col_name} = ?"
    return query_db(_conn, query, pg_args=pg_args)


@st.cache_data
def query_s3_event_list(_conn, pilot: str, model_id: str) -> list:
    """
    Query the list of events from the S3 bucket for a given ref ID.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        model_id (str): The HEC-RAS model ID to query.
    Returns:
        list: A list of simulated event IDs associated with the gage.
    """
    s3_path = f"s3://{pilot}/stac/prod-support/calibration/model={model_id}/"
    query = f"SELECT file FROM glob('{s3_path}**')"
    try:
        # Fetch as list of tuples, not DataFrame
        result = _conn.execute(query).fetchall()
        # Extract the next-level folder name after s3_path
        event_names = set()
        for row in result:
            rel = row[0][len(s3_path):].lstrip('/')
            if '/' in rel:
                folder = rel.split('/')[0]
                if "event=" in folder:
                    # Extract the event ID from the folder name
                    event = folder.split('=')[-1]
                    event_names.add(event)
        return sorted(event_names)
    except Exception as e:
        logger.error(f"Failed to list S3 folders: {e}")
        return []


@st.cache_data
def query_s3_obs_flow(_conn, pilot: str, gage_id: str, event_id: str) -> pd.DataFrame:
    """
    Query observed gage flow time series data from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        gage_id (str): The ID of the gage to query.
        event_id (str): The ID of the event to query.
    Returns:
        pd.DataFrame: A pandas DataFrame containing the observed gage flow data.
    """
    s3_path = f"s3://{pilot}/stac/prod-support/pq-test/**/data.pq"
    query = f"""SELECT datetime, flow as 'flow'
            FROM read_parquet('{s3_path}', hive_partitioning=true)
            WHERE gage='{gage_id}' and event='{event_id}';"""
    return query_db(_conn, query)


@st.cache_data
def query_s3_mod_wse(_conn, pilot: str, ref_id: str, ref_type: str, event_id: str) -> pd.DataFrame:
    """
    Query modeled water surface elevation (WSE) time series data from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        ref_id (str): The reference element ID to query (e.g., 'gage_usgs_08065200', 'nid_tx03268')
        ref_type (str): The type of reference element (e.g., 'ref_line', 'ref_point', 'bc_line').
        event_id (str): The ID of the event to query.
    Returns:
        pd.DataFrame: A pandas DataFrame containing the modeled flow data.
    """
    s3_path = f"s3://{pilot}/stac/prod-support/calibration/*/event=*/{ref_type}=*/wsel.pq"
    query = f"""SELECT time, {ref_type}, water_surface as wse
            FROM read_parquet('{s3_path}', hive_partitioning=true)
            WHERE event='{event_id}' and {ref_type}='{ref_id}';"""
    return query_db(_conn, query)


@st.cache_data
def query_s3_mod_flow(_conn, pilot: str, ref_id: str, ref_type: str, event_id: str) -> pd.DataFrame:
    """
    Query modeled flow time series data from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        ref_id (str): The reference element ID to query (e.g., 'gage_usgs_08065200', 'nid_tx03268')
        ref_type (str): The type of reference element (e.g., 'ref_line', 'ref_point', 'bc_line').
        event_id (str): The ID of the event to query.
    Returns:
        pd.DataFrame: A pandas DataFrame containing the modeled WSE data.
    """
    s3_path = f"s3://{pilot}/stac/prod-support/calibration/*/event=*/{ref_type}=*/flow.pq"
    query = f"""SELECT time, {ref_type}, flow as flow
            FROM read_parquet('{s3_path}', hive_partitioning=true)
            WHERE event='{event_id}' and {ref_type}='{ref_id}';"""
    return query_db(_conn, query)


@st.cache_data
def query_s3_mod_vel(_conn, pilot: str, ref_id: str, ref_type: str, event_id: str) -> pd.DataFrame:
    """
    Query modeled velocity time series data from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        ref_id (str): The reference element ID to query (e.g., 'gage_usgs_08065200', 'nid_tx03268')
        ref_type (str): The type of reference element (e.g., 'ref_line', 'ref_point', 'bc_line').
        event_id (str): The ID of the event to query.
    Returns:
        pd.DataFrame: A pandas DataFrame containing the modeled velocity data.
    """
    s3_path = f"s3://{pilot}/stac/prod-support/calibration/*/event=*/{ref_type}=*/velocity.pq"
    query = f"""SELECT time, {ref_type}, velocity as velocity
            FROM read_parquet('{s3_path}', hive_partitioning=true)
            WHERE event='{event_id}' and {ref_type}='{ref_id}';"""
    return query_db(_conn, query)

@st.cache_data
def query_s3_mod_stage(_conn, pilot: str, ref_id: str, ref_type: str, event_id: str) -> pd.DataFrame:
    """
    Query modeled stage time series data from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        ref_id (str): The reference element ID to query (e.g., 'gage_usgs_08065200', 'nid_tx03268')
        ref_type (str): The type of reference element (e.g., 'ref_line', 'ref_point', 'bc_line').
        event_id (str): The ID of the event to query.
    Returns:
        pd.DataFrame: A pandas DataFrame containing the modeled stage data.
    """
    s3_path = f"s3://{pilot}/stac/prod-support/calibration/*/event=*/{ref_type}=*/stage.pq"
    query = f"""SELECT time, {ref_type}, stage as stage
            FROM read_parquet('{s3_path}', hive_partitioning=true)
            WHERE event='{event_id}' and {ref_type}='{ref_id}';"""
    return query_db(_conn, query)


@st.cache_data
def query_s3_ref_lines(_conn, pilot: str, model_id: str) -> gpd.GeoDataFrame:
    """
    Query model reference line geometry data from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        model_id (str): The HEC-RAS model ID to query.
    Returns:
        gpd.GeoDataFrame: A GeoDataFrame containing the modeled geometry data.
    """
    if model_id == "all":
        s3_path = f"s3://{pilot}/stac/prod-support/calibration/*/data=geometry/ref_lines.pq"
    else:
        s3_path = f"s3://{pilot}/stac/prod-support/calibration/model={model_id}/data=geometry/ref_lines.pq"
    query = f"""SELECT * FROM read_parquet('{s3_path}', hive_partitioning=true);"""
    return query_db(_conn, query, layer="Reference Lines")


@st.cache_data
def query_s3_ref_points(_conn, pilot: str, model_id: str) -> gpd.GeoDataFrame:
    """
    Query model reference point geometry data from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        model_id (str): The HEC-RAS model ID to query.
    Returns:
        gpd.GeoDataFrame: A GeoDataFrame containing the reference points geometry data.
    """
    if model_id == "all":
        s3_path = f"s3://{pilot}/stac/prod-support/calibration/*/data=geometry/ref_points.pq"
    else:
        s3_path = f"s3://{pilot}/stac/prod-support/calibration/model={model_id}/data=geometry/ref_points.pq"
    query = f"""SELECT * FROM read_parquet('{s3_path}', hive_partitioning=true);"""
    return query_db(_conn, query, layer="Reference Points")


@st.cache_data
def query_s3_bc_lines(_conn, pilot: str, model_id: str) -> gpd.GeoDataFrame:
    """
    Query model boundary condition line geometry data from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        model_id (str): The HEC-RAS model ID to query.
    Returns:
        gpd.GeoDataFrame: A GeoDataFrame containing the boundary condition lines geometry data.
    """
    if model_id == "all":
        s3_path = f"s3://{pilot}/stac/prod-support/calibration/*/data=geometry/bc_lines.pq"
    else:
        s3_path = f"s3://{pilot}/stac/prod-support/calibration/model={model_id}/data=geometry/bc_lines.pq"
    query = f"""SELECT * FROM read_parquet('{s3_path}', hive_partitioning=true);"""
    return query_db(_conn, query, layer="BC Lines")


@st.cache_data
def query_s3_model_bndry(
    _conn, pilot: str, model_id: str
) -> gpd.GeoDataFrame:
    """
    Query model boundary geometry data from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        model_id (str): The HEC-RAS model ID to query.
    Returns:
        gpd.GeoDataFrame: A GeoDataFrame containing the model boundary geometry data.
    """
    if model_id == "all":
        s3_path = f"s3://{pilot}/stac/prod-support/calibration/*/data=geometry/model_geometry.pq"
    else:
        s3_path = f"s3://{pilot}/stac/prod-support/calibration/model={model_id}/data=geometry/model_geometry.pq"
    query = f"""SELECT * FROM read_parquet('{s3_path}', hive_partitioning=true);"""
    return query_db(_conn, query, layer="Basins")


@st.cache_data
def query_s3_model_thumbnail(_conn, pilot: str, model_id: str) -> str:
    """
    Query all thumbnail image files directly below the S3 model path.

    Parameters:
        _conn (connection): A DuckDB connection object (not used for image loading).
        pilot (str): The pilot name for the S3 bucket.
        model_id (str): The HEC-RAS model ID to query.
    Returns:
        file_path (str): The path to the thumbnail image file.
    """
    s3_path = f"s3://{pilot}/stac/prod-support/calibration/model={model_id}/"
    query = f"SELECT file FROM glob('{s3_path}*')"
    try:
        result = _conn.execute(query).fetchall()
        for row in result:
            file_path = row[0]
            rel_path = file_path[len(s3_path):]
            if rel_path.startswith("thumbnail."):
                return file_path
    except Exception as e:
        logger.error(f"Failed to list or read thumbnail files: {e}")

# if __name__ == "__main__":
#     from utils import create_pg_connection, create_s3_connection, get_pg_dsn
#     # Create connections
#     PG_CONNECTION = create_pg_connection()
#     S3_CONNECTION = create_s3_connection()
#     DSN = get_pg_dsn()
#     PILOT="trinity-pilot"
#     TEST_MODEL = "blw-elkhart"
#     TEST_REF_LINE_ID = 'gage_usgs_08065350'
#     EVENT_ID = "may2015"
#     GAGE_ID = "08062800"
#     TEST_PG_TABLE = "models_by_gage"
#     TEST_PG_SCHEMA = "flat_stac"

#     #Test querying model reference line geometry from S3
#     test_ref_line_geometry_df = query_s3_ref_lines(
#         S3_CONNECTION,  # S3 connection using DuckDB
#         PILOT,  # Pilot name for the S3 bucket
#         model_id=TEST_MODEL,  # HEC-RAS model ID
#     )
#     print(test_ref_line_geometry_df)
#     test_ref_line_geometry_df.to_parquet(f"/workspace/app/tests/data/parquet/{TEST_MODEL}_ref_line_geometry_df.parquet")

#     # Test querying model reference point geometry from S3
#     test_ref_pt_geometry_df = query_s3_ref_points(
#         S3_CONNECTION,  # S3 connection using DuckDB
#         PILOT,  # Pilot name for the S3 bucket
#         model_id=TEST_MODEL,  # HEC-RAS model ID
#     )
#     print(test_ref_pt_geometry_df)
#     test_ref_pt_geometry_df.to_parquet(f"/workspace/app/tests/data/parquet/{TEST_MODEL}_ref_pt_geometry_df.parquet")

#     # Test querying observed gage flow data from S3
#     test_obs_gage_flow_df = query_s3_obs_flow(
#         S3_CONNECTION,  # S3 connection using DuckDB
#         PILOT,  # Pilot name for the S3 bucket
#         gage_id=GAGE_ID,  # Example gage ID
#         event_id=EVENT_ID  # Example event ID
#     )
#     print(test_obs_gage_flow_df)
#     test_obs_gage_flow_df.to_csv(f"/workspace/app/tests/data/csv/{TEST_MODEL}_obs_flow_df.csv")

#     # Test querying modeled wse data from S3
#     test_mod_wse_df = query_s3_mod_wse(
#         S3_CONNECTION,  # S3 connection using DuckDB
#         PILOT,  # Pilot name for the S3 bucket
#         ref_id=TEST_REF_LINE_ID,  # Example reference element ID
#         event_id=EVENT_ID  # Example event ID
#     )
#     print(test_mod_wse_df)
#     test_mod_wse_df.to_csv(f"/workspace/app/tests/data/csv/{TEST_MODEL}_mod_wse_df.csv")

#     # Test querying modeled flow data from S3
#     test_mod_flow_df = query_s3_mod_flow(
#         S3_CONNECTION,  # S3 connection using DuckDB
#         PILOT,  # Pilot name for the S3 bucket
#         ref_id=TEST_REF_LINE_ID,  # Example reference element ID
#         event_id=EVENT_ID  # Example event ID
#     )
#     print(test_mod_flow_df)
#     test_mod_flow_df.to_csv(f"/workspace/app/tests/data/csv/{TEST_MODEL}_mod_flow_df.csv")

#     # Test querying all rows from a Postgres table
#     test_models_by_gage_gdf = query_pg_table_all(
#         PG_CONNECTION,  # Postgres connection using DuckDB
#         DSN,  # DSN credentials for the PostgreSQL database
#         TEST_PG_SCHEMA,  # Schema name where the table is located
#         TEST_PG_TABLE  # Table name to query
#     )
#     print(test_models_by_gage_gdf)
#     test_models_by_gage_gdf.to_parquet(f"/workspace/app/tests/data/parquet/{TEST_PG_TABLE}_all.parquet")

#     # Test querying filtered rows from a Postgres table
#     test_models_by_gage_filtered_gdf = query_pg_table_filter(
#         PG_CONNECTION,  # Postgres connection using DuckDB
#         DSN,  # DSN credentials for the PostgreSQL database
#         TEST_PG_SCHEMA,  # Schema name where the table is located
#         TEST_PG_TABLE,  # Table name to query
#         col_name="gage_id",  # Column to filter by
#         search_id=GAGE_ID  # ID to filter the column by
#     )
#     print(test_models_by_gage_filtered_gdf)
#     test_models_by_gage_filtered_gdf.to_parquet(f"/workspace/app/tests/data/parquet/{TEST_PG_TABLE}_filtered.parquet")
