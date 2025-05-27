import pandas as pd
import geopandas as gpd
import streamlit as st
import shapely.wkb

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
    df["geometry"] = df["geometry"].apply(lambda x: shapely.wkb.loads(bytes.fromhex(x)))
    gdf = gpd.GeoDataFrame(df, geometry="geometry")
    # Set the CRS to EPSG:4326
    gdf.set_crs(epsg=4326, inplace=True)
    # Convert the geometry to EPSG:4326
    gdf = gdf.to_crs(epsg=4326)
    return gdf

@st.cache_data
def get_gages_summary(_p_conn):
    """
    Query the database for a summary table of gages

    Parameters:
        _p_conn (connection): A psycopg2 connection object.

    Returns:
        gdf (GeoDataFrame): A GeoDataFrame containing the rows returned from the query.
    """
    # Create a cursor object
    cur = _p_conn.cursor()

    # SQL query to execute: select all rows from the materialized view gages_summary
    query = "SELECT * FROM flat_stac.gages_summary"

    try:
        # Execute the query
        cur.execute(query)
        # Fetch all rows from the table
        rows = cur.fetchall()
        headers = [desc[0] for desc in cur.description]
        df = pd.DataFrame(rows, columns=headers)
        gdf = format_to_gdf(df)
        return gdf
    except Exception as e:
        # Rollback the transaction in case of an error
        _p_conn.rollback()
        print(f"An error occurred: {e}")
        return None
    finally:
        # Close the cursor
        cur.close()

@st.cache_data
def get_storms_summary(_p_conn):
    """
    Query the database for a summary table of storms

    Parameters:
        _p_conn (connection): A psycopg2 connection object.

    Returns:
        gdf (GeoDataFrame): A GeoDataFrame containing the rows returned from the query.
    """
    # Create a cursor object
    cur = _p_conn.cursor()

    # SQL query to execute: select all rows from the materialized view storms_summary
    query = "SELECT * FROM flat_stac.storms_summary"

    try:
        # Execute the query
        cur.execute(query)
        # Fetch all rows from the table
        rows = cur.fetchall()
        headers = [desc[0] for desc in cur.description]
        df = pd.DataFrame(rows, columns=headers)
        gdf = format_to_gdf(df)
        return gdf
    except Exception as e:
        # Rollback the transaction in case of an error
        _p_conn.rollback()
        print(f"An error occurred: {e}")
        return None
    finally:
        # Close the cursor
        cur.close()

@st.cache_data
def get_gages_by_model_id(_p_conn, model_id):
    """
    Query the database for gages by model ID

    Parameters:
        _p_conn (connection): A psycopg2 connection object.
        model_id (int): The model ID to filter the gages.

    Returns:
        gdf (GeoDataFrame): A GeoDataFrame containing the rows returned from the query.
    """
    # Create a cursor object
    cur = _p_conn.cursor()

    # SQL query to execute: select all rows from the materialized view gages_by_model_id
    query = "SELECT * FROM flat_stac.gages_by_model_id WHERE model_id = %s"

    try:
        # Execute the query with the model_id parameter to prevent SQL injection
        cur.execute(query, (model_id,))
        # Fetch all rows from the table
        rows = cur.fetchall()
        headers = [desc[0] for desc in cur.description]
        df = pd.DataFrame(rows, columns=headers)
        gdf = format_to_gdf(df)
        return gdf
    except Exception as e:
        # Rollback the transaction in case of an error
        _p_conn.rollback()
        print(f"An error occurred: {e}")
        return None
    finally:
        # Close the cursor
        cur.close()
