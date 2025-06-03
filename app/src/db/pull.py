import pandas as pd
import geopandas as gpd
import streamlit as st
import shapely.wkb

def query_df(_conn, query: str, geometry_type: str = None) -> pd.DataFrame:
    """
    Execute a SQL query and return the result as a pandas DataFrame.

    Parameters:
        _conn (connection): A DuckDB connection object.
        query (str): The SQL query to execute.
        geometry_type (str, optional): The type of geometry to query. Either reference lines or reference points.

    Returns:
        df (DataFrame): A pandas DataFrame containing the rows returned from the query.
    """
    try:
        # NOTE: A /UTC error occurs when using fetchdf() with duckdb
        df = _conn.execute(query).fetchnumpy()
        # Convert the numpy array to a pandas DataFrame
        df = pd.DataFrame(df)
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
            df = format_to_gdf(df, geometry_type)
        return df
    except Exception as e:
        raise ValueError(
            f"An error occurred when querying the database: {e}"
        ) from e

def format_to_gdf(df: pd.DataFrame, layer_name: str) -> gpd.GeoDataFrame:
    """
    Convert a pandas DataFrame to a GeoDataFrame with EPSG:4326 CRS.

    Parameters:
        df (DataFrame): A pandas DataFrame containing geometry in WKB format.
        layer_name (str): The name of the layer to assign as a column in the GeoDataFrame.

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
    gdf["layer"] = layer_name
    return gdf


@st.cache_data
def pull_from_db(
    _conn,
    dsn,
    table_name,
    layer_name,
    schema_name="flat_stac",
    col_name=None,
    search_id=None,
):
    """
    Query the Postgres database

    Parameters:
        _conn (connection): A DuckDB connection object.
        dsn (str): The Data Source Name (DSN) for the PostgreSQL database.
        table_name (str): The name of the table to query.
        layer_name (str): The name of the layer to assign as a column in the DataFrame.
        schema_name (str): The name of the schema where the table is located. Default is "flat_stac".
        col_name (str): The name of the column to filter the query. Default is None.
        search_id (int): The ID to filter the query. Default is None.

    Returns:
        gdf (GeoDataFrame): A GeoDataFrame containing the rows returned from the query.
    """
    try:
        # NOTE: A /UTC error occurs when using fetchdf() with duckdb
        if col_name is None or search_id is None:
            # Select all rows from the table
            df = _conn.execute(
                "SELECT * FROM postgres_scan(?, ?, ?)", [dsn, schema_name, table_name]
            ).fetchnumpy()
        elif col_name is not None and search_id is not None:
            # If col_name and search_id are provided, filter the query
            df = _conn.execute(
                f"SELECT * FROM postgres_scan(?, ?, ?) WHERE {col_name} = ?",
                [dsn, schema_name, table_name, search_id],
            ).fetchnumpy()
        else:
            raise ValueError(
                "Either col_name and search_id must be provided or both must be None."
            )
        # Convert the numpy array to a pandas DataFrame
        df = pd.DataFrame(df)
        if "geometry" in df.columns:
            # Convert the DataFrame to a GeoDataFrame
            df = format_to_gdf(df, layer_name)
        return df
    except Exception as e:
        print(f"An unkown error occurred when querying the database: {e}")
        st.error(f"An unkown error occurred when querying the database: {e}")
        return None


@st.cache_data
def pull_from_s3(_conn,
                 query_type,
                 var_type=None,
                 event_id=None,
                 gage_id=None,
                 ref_id=None,
                 model_id=None,
                 geometry_type=None):
    """
    Query the s3 bucket as a DuckDB table.

    Parameters:
        _conn (connection): A DuckDB connection object.
        query_type (str): The type of query. Must be either 'observed', 'modeled', or 'geometry'.
        var_type (str, optional): The type of variable to query. Must be either 'flow' or 'wse'.
        event_id (str, optional): The ID of the event to query. (e.g., dec1991)
        gage_id (str, optional): The ID of the gage to query. (e.g., '08045850')
        ref_id (str, optional): The reference line ID for modeled time series data.
        model_id (str, optional): The model ID
        geometry_type (str, optional): The type of geometry to query. Either reference lines or reference points.

    Returns:
        df (DataFrame): A pandas DataFrame containing the time series data for the specified gage and event.
    """
    if query_type == "observed":
        if any([gage_id, event_id]) is None:
            raise ValueError(
                "gage_id and event_id must be provided for observed time series data."
            )
        s3_path = "s3://trinity-pilot/stac/prod-support/pq-test/**/data.pq"
        query = f"""SELECT datetime, {var_type} as '{var_type}'
                FROM read_parquet('{s3_path}', hive_partitioning=true)
                WHERE gage='{gage_id}' and event='{event_id}';"""

    elif query_type == "modeled":
        if any([gage_id, event_id]) is None:
            raise ValueError(
                "ref_id and gage_id must be provided for modeled time series data."
            )
        if var_type == "wse":
            s3_path = "s3://trinity-pilot/stac/prod-support/results/**/wsel.pq"
            query = f"""SELECT time, ref_id, water_surface as wse
                        FROM read_parquet('{s3_path}', hive_partitioning=true)
                        WHERE event='{event_id}' and ref_id='{ref_id}';"""
        elif var_type == "flow":
            s3_path = "s3://trinity-pilot/stac/prod-support/results/**/flow.pq"
            query = f"""SELECT time, ref_id, flow as flow
                        FROM read_parquet('{s3_path}', hive_partitioning=true)
                        WHERE event='{event_id}' and ref_id='{ref_id}';"""
        else:
            raise ValueError(
                "var_type must be either 'flow' or 'wse' for modeled time series data."
            )
    elif query_type =="geometry":
        if model_id is None or geometry_type is None:
            raise ValueError("model_id and geometry_type must be provided for querying geometry data.")
        if geometry_type == "Reference Lines":
            s3_path = f"s3://trinity-pilot/stac/prod-support/calibration/model={model_id}/data=geometry/ref_lines.pq"
        else:
            s3_path = f"s3://trinity-pilot/stac/prod-support/calibration/model={model_id}/data=geometry/ref_points.pq"
        query = f"""SELECT * FROM read_parquet('{s3_path}', hive_partitioning=true);"""
    else:
        raise ValueError("Invalid query_type. Must be 'observed', 'modeled' or 'geometry.")

    if query_type == "observed" or query_type == "modeled":
        df = query_df(_conn, query)
    elif query_type == "geometry":
        df = query_df(_conn, query, geometry_type)
    else:
        raise ValueError("Invalid query_type. Must be 'observed', 'modeled' or 'geometry'.")
    
    return df
