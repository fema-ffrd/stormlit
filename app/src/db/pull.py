import io
import pandas as pd
import geopandas as gpd
import streamlit as st
import shapely.wkb
import duckdb
import s3fs
from PIL import Image
import logging

logger = logging.getLogger(__name__)


class StormlitQueryException(Exception):
    pass


def s3_path_exists(s3_path: str) -> bool:
    """
    Check if a given S3 path exists.

    Parameters:
        s3_path (str): The S3 path to check.

    Returns:
        bool: True if the S3 path exists, False otherwise.
    """
    fs = s3fs.S3FileSystem(anon=False)
    return fs.exists(s3_path)


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


def query_db(
    _conn, query: str, pg_args: list = None, layer: str = None
) -> pd.DataFrame | gpd.GeoDataFrame:
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
        df = df.sort_values(by="time").drop_duplicates(subset=["time"])
    if "time" in df.columns:
        # Convert time column to pandas datetime
        df["time"] = pd.to_datetime(df["time"])
        df = df.sort_values(by="time").drop_duplicates(subset=["time"])
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
def query_s3_calibration_event_list(_conn, pilot: str, model_id: str) -> list:
    """
    Query the list of calibration events from the S3 bucket for a given model ID.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        model_id (str): The HEC-RAS model ID to query.
    Returns:
        list: A list of simulated event IDs associated with the gage.
    """
    s3_path = f"s3://{pilot}/stac/prod-support/calibration/model={model_id}/"
    if s3_path_exists(s3_path):
        query = f"SELECT file FROM glob('{s3_path}**')"
        try:
            # Fetch as list of tuples, not DataFrame
            result = _conn.execute(query).fetchall()
            # Extract the next-level folder name after s3_path
            event_names = set()
            for row in result:
                rel = row[0][len(s3_path) :].lstrip("/")
                if "/" in rel:
                    folder = rel.split("/")[0]
                    if "event=" in folder:
                        # Extract the event ID from the folder name
                        event = folder.split("=")[-1]
                        event_names.add(event)
            return sorted(event_names)
        except Exception as e:
            msg = f"DuckDB S3 Error: {e}"
            logger.error(msg)
            raise StormlitQueryException(msg) from e
    else:
        msg = f"S3 path does not exist. Please verify the path and its contents: {s3_path}"
        logger.error(msg)
        raise StormlitQueryException(msg)


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
    s3_path = f"s3://{pilot}/stac/prod-support/pq-test/*/*/data.pq"
    query = f"""SELECT datetime, flow as 'obs_flow'
            FROM read_parquet('{s3_path}', hive_partitioning=true)
            WHERE gage='{gage_id}' and event='{event_id}';"""
    return query_db(_conn, query)


@st.cache_data
def query_s3_mod_wse(
    _conn, pilot: str, ref_id: str, ref_type: str, event_id: str, model_id: str
) -> pd.DataFrame:
    """
    Query modeled water surface elevation (WSE) time series data from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        ref_id (str): The reference element ID to query (e.g., 'gage_usgs_08065200', 'nid_tx03268')
        ref_type (str): The type of reference element (e.g., 'ref_line', 'ref_point', 'bc_line').
        event_id (str): The ID of the event to query.
        model_id (str): The HEC-RAS model ID to query.
    Returns:
        pd.DataFrame: A pandas DataFrame containing the modeled flow data.
    """
    s3_path = f"s3://{pilot}/stac/prod-support/calibration/model={model_id}/event={event_id}/{ref_type}={ref_id}/wsel.pq"
    if s3_path_exists(s3_path):
        query = f"""SELECT time, {ref_type}, water_surface as wse
                FROM read_parquet('{s3_path}', hive_partitioning=true);"""
        return query_db(_conn, query)
    else:
        msg = f"S3 path does not exist. Please verify the path and its contents: {s3_path}"
        logger.error(msg)
        raise StormlitQueryException(msg)


@st.cache_data
def query_s3_mod_flow(
    _conn, pilot: str, ref_id: str, ref_type: str, event_id: str, model_id: str
) -> pd.DataFrame:
    """
    Query modeled flow time series data from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        ref_id (str): The reference element ID to query (e.g., 'gage_usgs_08065200', 'nid_tx03268')
        ref_type (str): The type of reference element (e.g., 'ref_line', 'ref_point', 'bc_line').
        event_id (str): The ID of the event to query.
        model_id (str): The HEC-RAS model ID to query.
    Returns:
        pd.DataFrame: A pandas DataFrame containing the modeled WSE data.
    """
    s3_path = f"s3://{pilot}/stac/prod-support/calibration/model={model_id}/event={event_id}/{ref_type}={ref_id}/flow.pq"
    if s3_path_exists(s3_path):
        query = f"""SELECT time, {ref_type}, flow as flow
                FROM read_parquet('{s3_path}', hive_partitioning=true);"""
        return query_db(_conn, query)
    else:
        msg = f"S3 path does not exist. Please verify the path and its contents: {s3_path}"
        logger.error(msg)
        raise StormlitQueryException(msg)


@st.cache_data
def query_s3_mod_vel(
    _conn, pilot: str, ref_id: str, ref_type: str, event_id: str, model_id: str
) -> pd.DataFrame:
    """
    Query modeled velocity time series data from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        ref_id (str): The reference element ID to query (e.g., 'gage_usgs_08065200', 'nid_tx03268')
        ref_type (str): The type of reference element (e.g., 'ref_line', 'ref_point', 'bc_line').
        event_id (str): The ID of the event to query.
        model_id (str): The HEC-RAS model ID to query.
    Returns:
        pd.DataFrame: A pandas DataFrame containing the modeled velocity data.
    """
    s3_path = f"s3://{pilot}/stac/prod-support/calibration/model={model_id}/event={event_id}/{ref_type}={ref_id}/velocity.pq"
    if s3_path_exists(s3_path):
        query = f"""SELECT time, {ref_type}, velocity as velocity
                FROM read_parquet('{s3_path}', hive_partitioning=true);"""
        return query_db(_conn, query)
    else:
        msg = f"S3 path does not exist. Please verify the path and its contents: {s3_path}"
        logger.error(msg)
        raise StormlitQueryException(msg)


@st.cache_data
def query_s3_mod_stage(
    _conn, pilot: str, ref_id: str, ref_type: str, event_id: str, model_id: str
) -> pd.DataFrame:
    """
    Query modeled stage time series data from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        ref_id (str): The reference element ID to query (e.g., 'gage_usgs_08065200', 'nid_tx03268')
        ref_type (str): The type of reference element (e.g., 'ref_line', 'ref_point', 'bc_line').
        event_id (str): The ID of the event to query.
        model_id (str): The HEC-RAS model ID to query.
    Returns:
        pd.DataFrame: A pandas DataFrame containing the modeled stage data.
    """
    s3_path = f"s3://{pilot}/stac/prod-support/calibration/model={model_id}/event={event_id}/{ref_type}={ref_id}/stage.pq"
    if s3_path_exists(s3_path):
        query = f"""SELECT time, {ref_type}, stage as stage
                FROM read_parquet('{s3_path}', hive_partitioning=true);"""
        return query_db(_conn, query)
    else:
        msg = f"S3 path does not exist. Please verify the path and its contents: {s3_path}"
        logger.error(msg)
        raise StormlitQueryException(msg)


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
        s3_path = (
            f"s3://{pilot}/stac/prod-support/calibration/*/data=geometry/ref_lines.pq"
        )
    else:
        s3_path = f"s3://{pilot}/stac/prod-support/calibration/model={model_id}/data=geometry/ref_lines.pq"
    query = f"""SELECT * FROM read_parquet('{s3_path}', hive_partitioning=true);"""
    return query_db(_conn, query, layer="Reference Line")


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
        s3_path = (
            f"s3://{pilot}/stac/prod-support/calibration/*/data=geometry/ref_points.pq"
        )
    else:
        s3_path = f"s3://{pilot}/stac/prod-support/calibration/model={model_id}/data=geometry/ref_points.pq"

    query = f"""SELECT * FROM read_parquet('{s3_path}', hive_partitioning=true);"""
    return query_db(_conn, query, layer="Reference Point")


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
        s3_path = (
            f"s3://{pilot}/stac/prod-support/calibration/*/data=geometry/bc_lines.pq"
        )
    else:
        s3_path = f"s3://{pilot}/stac/prod-support/calibration/model={model_id}/data=geometry/bc_lines.pq"
    query = f"""SELECT * FROM read_parquet('{s3_path}', hive_partitioning=true);"""
    return query_db(_conn, query, layer="BC Line")


@st.cache_data
def query_s3_model_bndry(_conn, pilot: str, model_id: str) -> gpd.GeoDataFrame:
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
    return query_db(_conn, query, layer="Model")


@st.cache_data
def query_s3_model_thumbnail(_conn, pilot: str, model_id: str) -> Image:
    """
    Query a thumbnail image file directly below the S3 model path.

    Parameters:
        _conn (connection): A DuckDB connection object (not used for image loading).
        pilot (str): The pilot name for the S3 bucket.
        model_id (str): The HEC-RAS model ID to query.
    Returns:
        Image: A PIL Image object containing the thumbnail image.
    """
    s3_path = f"s3://{pilot}/stac/prod-support/calibration/model={model_id}/"
    if s3_path_exists(s3_path):
        query = f"SELECT file FROM glob('{s3_path}*')"
        try:
            result = _conn.execute(query).fetchall()
            for row in result:
                file_path = row[0]
                rel_path = file_path[len(s3_path) :]
                if rel_path.startswith("thumbnail."):
                    fs = s3fs.S3FileSystem(anon=False)
                    with fs.open(file_path, "rb") as f:
                        img_bytes = f.read()
                        return Image.open(io.BytesIO(img_bytes)).copy()
        except Exception as e:
            msg = f"DuckDB S3 Error: {e}"
            logger.error(msg)
            raise StormlitQueryException(msg) from e
    else:
        msg = f"S3 path does not exist. Please verify the path and its contents: {s3_path}"
        logger.error(msg)
        raise StormlitQueryException(msg)


@st.cache_data
def query_s3_stochastic_storm_list(
    _conn, pilot: str, element_id: str = "amon-g-carter_s010"
) -> list:
    """
    Query the list of stochastic storm events from the S3 bucket for a given HMS element ID.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
    Returns:
        list: A list of simulated event IDs associated with the gage.
    """
    s3_path = f"s3://{pilot}/cloud-hms-db/simulations/element={element_id}/"
    if s3_path_exists(s3_path):
        query = f"SELECT file FROM glob('{s3_path}**')"
        try:
            # Fetch as list of tuples, not DataFrame
            result = _conn.execute(query).fetchall()
            # Extract the next-level folder name after s3_path
            storm_ids = set()
            for row in result:
                rel = row[0][len(s3_path) :].lstrip("/")
                if "/" in rel:
                    folder = rel.split("/")[0]
                    if "storm_id=" in folder:
                        # Extract the event ID from the folder name
                        storm = folder.split("=")[-1]
                        storm_ids.add(storm)
            return sorted(storm_ids)
        except Exception as e:
            msg = f"DuckDB S3 Error: {e}"
            logger.error(msg)
            raise StormlitQueryException(msg) from e
    else:
        msg = f"S3 path does not exist. Please verify the path and its contents: {s3_path}"
        logger.error(msg)
        raise StormlitQueryException(msg)


@st.cache_data
def query_s3_stochastic_event_list(
    _conn, pilot: str, element_id: str, storm_id: str
) -> list:
    """
    Query the list of stochastic events from the S3 bucket for a given element ID and storm ID.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        element_id (str): The element ID to query.
        storm_id (str): The storm ID to query.
    Returns:
        list: A list of simulated event IDs associated with the element ID and storm ID.
    """
    s3_path = f"s3://{pilot}/cloud-hms-db/simulations/element={element_id}/storm_id={storm_id}/"
    if s3_path_exists(s3_path):
        query = f"SELECT file FROM glob('{s3_path}**')"
        try:
            # Fetch as list of tuples, not DataFrame
            result = _conn.execute(query).fetchall()
            # Extract the next-level folder name after s3_path
            event_ids = set()
            for row in result:
                rel = row[0][len(s3_path) :].lstrip("/")
                if "/" in rel:
                    folder = rel.split("/")[0]
                    if "event_id=" in folder:
                        # Extract the event ID from the folder name
                        event = folder.split("=")[-1]
                        event_ids.add(event)
            return sorted(event_ids)
        except Exception as e:
            msg = f"DuckDB S3 Error: {e}"
            logger.error(msg)
            raise StormlitQueryException(msg) from e
    else:
        msg = f"S3 path does not exist. Please verify the path and its contents: {s3_path}"
        logger.error(msg)
        raise StormlitQueryException(msg)


@st.cache_data
def query_s3_stochastic_hms_flow(
    _conn, pilot: str, element_id: str, storm_id: str, event_id: str, flow_type: str
) -> pd.DataFrame:
    """
    Query stochastic HMS flow timeseries data from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        element_id (str): The element ID to query (e.g., 'amon-g-carter_s010').
        storm_id (str): The storm ID to query (e.g., '19790222').
        event_id (str): The event ID to query (e.g., '13094').
        flow_type (str): The type of flow data to query (e.g., 'FLOW', 'FLOW-BASE').
    Returns:
        pd.DataFrame: A pandas DataFrame containing the stochastic HMS flow data.
    """
    s3_path = f"s3://{pilot}/cloud-hms-db/simulations/element={element_id}/storm_id={storm_id}/event_id={event_id}/{flow_type}.pq"
    if s3_path_exists(s3_path):
        query = f"""SELECT datetime, values as hms_flow
                FROM read_parquet('{s3_path}', hive_partitioning=true);"""
        return query_db(_conn, query)
    else:
        msg = f"S3 path does not exist. Please verify the path and its contents: {s3_path}"
        logger.error(msg)
        st.warning(msg)
        return pd.DataFrame()


@st.cache_data
def query_s3_ensemble_peak_flow(
    _conn,
    pilot: str,
    realization_id: int,
    element_id: str,
    block_group_start: int,
    block_group_end: int,
) -> pd.DataFrame:
    """
    Query stochastic block group peak flow data from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        realization_id (int): The realization ID to query (e.g., 1).
        element_id (str): The element ID to query (e.g., 'amon-g-carter_s010').
        block_group_start (int): The starting block group index to query.
        block_group_end (int): The ending block group index to query.
    Returns:
        pd.DataFrame: A pandas DataFrame containing the stochastic block group flow data.
    """
    s3_paths = [
        f"s3://{pilot}/cloud-hms-db/ams/realization={realization_id}/block_group={i}/peaks.pq"
        for i in range(block_group_start, block_group_end + 1)
    ]
    paths_str = ", ".join([f"'{p}'" for p in s3_paths])
    # Construct the query to read from multiple S3 paths
    query = f"""
        SELECT
            block_group,
            MAX(peak_flow) AS peak_flow,
            ARG_MAX(event_id, peak_flow) AS event_id
        FROM read_parquet([{paths_str}], hive_partitioning=true)
        WHERE element='{element_id}'
        GROUP BY block_group
        ORDER BY peak_flow DESC;
    """
    return query_db(_conn, query)


@st.cache_data
def query_s3_ams_peaks_by_element(
    _conn, pilot: str, element_id: str, realization_id: int
) -> pd.DataFrame:
    """
    Query stochastic AMS peak flow data by element from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        element_id (str): The element ID to query (e.g., 'amon-g-carter_s010').
        realization_id (int): The realization ID to query (e.g., 1).
    Returns:
        pd.DataFrame: A pandas DataFrame containing the stochastic AMS peak flow data.
    """
    s3_path = (
        f"s3://{pilot}/cloud-hms-db/ams/realization={realization_id}/ams_by_elements.pq"
    )
    if s3_path_exists(s3_path):
        query = f"""SELECT ROW_NUMBER() OVER (ORDER BY peak_flow DESC) AS rank,
                element, peak_flow, event_id, block_group
                FROM read_parquet('{s3_path}', hive_partitioning=true)
                WHERE element='{element_id}';"""
        return query_db(_conn, query)
    else:
        msg = f"S3 path does not exist. Please verify the path and its contents: {s3_path}"
        logger.error(msg)
        raise StormlitQueryException(msg)


@st.cache_data
def query_s3_hms_storms(_conn, pilot: str) -> pd.DataFrame:
    """
    Query the list of HMS storms from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
    Returns:
        pd.DataFrame: A pandas DataFrame containing the HMS storm data.
    """
    s3_path = f"s3://{pilot}/cloud-hms-db/storms.pq"
    if s3_path_exists(s3_path):
        query = f"SELECT event_number as event_id, storm_id, storm_type FROM read_parquet('{s3_path}', hive_partitioning=true);"
        return query_db(_conn, query)
    else:
        msg = f"S3 path does not exist. Please verify the path and its contents: {s3_path}"
        logger.error(msg)
        raise StormlitQueryException(msg)


@st.cache_data
def query_s3_gage_ams(_conn, pilot: str, gage_id: str) -> pd.DataFrame:
    """
    Query AMS gage data from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        gage_id (str): The ID of the gage to query.
    Returns:
        pd.DataFrame: A pandas DataFrame containing the AMS gage data.
    """
    s3_path = f"s3://{pilot}/stac/prod-support/gages/{gage_id}/{gage_id}-ams.pq"
    if s3_path_exists(s3_path):
        query = f"""
            SELECT
                peak_va as peak_flow,
                gage_ht,
                site_no as gage_id,
                datetime as peak_time,
                ROW_NUMBER() OVER (ORDER BY peak_flow DESC) AS rank
            FROM read_parquet('{s3_path}', hive_partitioning=true);
        """
        return query_db(_conn, query)
    else:
        msg = f"S3 path does not exist. Please verify the path and its contents: {s3_path}"
        logger.error(msg)
        return pd.DataFrame()


@st.cache_data
def query_s3_hms_gages_lookup(
    _conn, pilot: str,
) -> gpd.GeoDataFrame:
    """
    Query HMS gages lookup geodataframe from the S3 bucket.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
    Returns:
        pd.DataFrame: A pandas DataFrame containing the HMS gage lookup data.
    """
    s3_path = f"s3://{pilot}/stac/prod-support/gages/hms_gages_lookup.parquet"
    if s3_path_exists(s3_path):
        query = f"SELECT * FROM read_parquet('{s3_path}', hive_partitioning=true);"
        return query_db(_conn, query)
    else:
        msg = f"S3 path does not exist. Please verify the path and its contents: {s3_path}"
        logger.error(msg)
        raise StormlitQueryException(msg)

@st.cache_data
def query_s3_ams_confidence_limits(
    _conn, pilot: str, gage_id: str, realization_id: int, duration: str, variable: str
) -> pd.DataFrame:
    """
    Query confidence limits data from the S3 bucket for a given gage ID.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        gage_id (str): The gage ID to query.
        realization_id (int): The realization ID to query (e.g., 1).
        duration (str): The duration of the confidence limits (e.g., '1Hour', '24Hour', '72Hour').
        variable (str): The variable to query (e.g., 'Flow', 'Elev').
    Returns:
        pd.DataFrame: A pandas DataFrame containing the confidence limits data.
    """
    s3_path = f"s3://{pilot}/cloud-hms-db/ams/realization={realization_id}/confidence_limits.parquet"
    if s3_path_exists(s3_path):
        query = f"SELECT * FROM read_parquet('{s3_path}', hive_partitioning=true) WHERE duration='{duration}' and site_no='{gage_id}' and variable='{variable}';"
        return query_db(_conn, query)
    else:
        msg = f"S3 path does not exist. Please verify the path and its contents: {s3_path}"
        logger.error(msg)
        raise StormlitQueryException(msg)