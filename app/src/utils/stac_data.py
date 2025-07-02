import os
import geopandas as gpd
import streamlit as st
import requests
import json
from PIL import Image
from io import BytesIO

from db.pull import (
    query_s3_ref_points,
    query_s3_ref_lines,
    query_s3_bc_lines,
    query_s3_model_bndry,
)

rootDir = os.path.dirname(os.path.abspath(__file__))  # located within utils folder
srcDir = os.path.abspath(os.path.join(rootDir, ".."))  # go up one level to src
assetsDir = os.path.abspath(os.path.join(srcDir, "assets"))  # go up one level to src


def prep_gdf(gdf: gpd.GeoDataFrame, layer: str, hms: bool = False) -> gpd.GeoDataFrame:
    """
    Prepares a GeoDataFrame for plotting on a folium map.

    Parameters
    ----------
    gdf: gpd.GeoDataFrame
        A GeoDataFrame containing the map data
    layer: str
        The name of the layer
    hms: bool, optional
        Whether the layer is an HMS layer (default is False).

    Returns
    -------
    gpd.GeoDataFrame
        A GeoDataFrame with the necessary columns for plotting on a folium map
    """
    # Get the original CRS and bbox
    crs_str = gdf.crs.to_string()
    bbox = gdf.total_bounds
    bbox_str = f"{bbox[0]:.7f},{bbox[1]:.7f},{bbox[2]:.7f},{bbox[3]:.7f}"
    # Convert the CRS to EPSG:4326
    gdf = gdf.to_crs(epsg=4326)
    # Find the center of the map data
    centroids = gdf.geometry.centroid
    gdf["lat"] = centroids.y.astype(float)
    gdf["lon"] = centroids.x.astype(float)
    gdf["layer"] = layer
    gdf["crs"] = crs_str
    gdf["bbox"] = bbox_str
    if hms:
        if "name" in gdf.columns:
            gdf.rename(columns={"name": "hms_element"}, inplace=True)
    return gdf


def init_pilot(s3_conn, pilot: str):
    """
    Initialize the map data for the selected pilot study

    Parameters
    ----------
    s3_conn: duckdb.DuckDBPyConnection
        The connection to the S3 account
    pilot: str
        The name of the pilot study to initialize data for
    """
    if pilot == "trinity-pilot":
        st.pilot_base_url = f"https://{pilot}.s3.amazonaws.com/stac/prod-support"
        ## TODO: Need to add local data to a STAC catalog
        st.pilot_layers = {
            "Dams": f"{st.pilot_base_url}/dams/non-usace/non-usace-dams.geojson",
            "Gages": f"{st.pilot_base_url}/gages/gages.geojson",
            "Subbasins": f"{st.pilot_base_url}/conformance/hydrology/trinity/assets/Subbasin.geojson",
            "Reaches": f"{st.pilot_base_url}/conformance/hydrology/trinity/assets/Reach.geojson",
            "Junctions": f"{st.pilot_base_url}/conformance/hydrology/trinity/assets/Junction.geojson",
            "Reservoirs": f"{st.pilot_base_url}/conformance/hydrology/trinity/assets/Reservoir.geojson",
        }
        st.cog_layers = {}
    else:
        raise ValueError(f"Error: invalid pilot study {pilot}")

    df_dams = gpd.read_file(st.pilot_layers["Dams"])
    st.dams = prep_gdf(df_dams, "Dam")
    df_gages = gpd.read_file(st.pilot_layers["Gages"]).drop_duplicates()
    st.gages = prep_gdf(df_gages, "Gage")
    st.models = query_s3_model_bndry(s3_conn, pilot, "all")
    st.ref_lines = query_s3_ref_lines(s3_conn, pilot, "all")
    st.ref_points = query_s3_ref_points(s3_conn, pilot, "all")
    st.bc_lines = query_s3_bc_lines(s3_conn, pilot, "all")
    df_subbasins = gpd.read_file(st.pilot_layers["Subbasins"])
    st.subbasins = prep_gdf(df_subbasins, "Subbasin", hms=True)
    df_reaches = gpd.read_file(st.pilot_layers["Reaches"])
    st.reaches = prep_gdf(df_reaches, "Reach", hms=True)
    df_junctions = gpd.read_file(st.pilot_layers["Junctions"])
    st.junctions = prep_gdf(df_junctions, "Junction", hms=True)
    df_reservoirs = gpd.read_file(st.pilot_layers["Reservoirs"])
    st.reservoirs = prep_gdf(df_reservoirs, "Reservoir", hms=True)


def define_gage_data(gage_id: str):
    """
    Define the gage data for the selected gage
    """
    gage_data = {
        "Metadata": f"{st.pilot_base_url}/gages/{gage_id}/{gage_id}.json",
        "Flow Stats": f"{st.pilot_base_url}/gages/{gage_id}/{gage_id}-flow-stats.png",
        "AMS": f"{st.pilot_base_url}/gages/{gage_id}/{gage_id}-ams.png",
        "AMS Seasons": f"{st.pilot_base_url}/gages/{gage_id}/{gage_id}-ams-seasonal.png",
        "AMS LP3": f"{st.pilot_base_url}/gages/{gage_id}/{gage_id}-ams-lpiii.png",
    }
    return gage_data


def define_storm_data(storm_id: str):
    """
    Define the storm data for the selected storm
    """
    storm_data = {
        "Metadata": f"{st.pilot_base_url}/storms/72hr-events/{storm_id}/{storm_id}.json",
    }
    return storm_data


def define_dam_data(dam_id: str):
    """
    Define the dam data for the selected dam
    """
    dam_data = {
        "Metadata": f"{st.pilot_base_url}/dams/non-usace/{dam_id}/{dam_id}.json",
    }
    return dam_data


@st.cache_data
def get_stac_img(plot_url: str):
    """
    Get the image from the STAC API

    Parameters
    ----------
    plot_url: str
        The URL of the image to get
    Returns
    -------
    bool
        True if the image was successfully retrieved, False otherwise
    Image
        The image object if successful, None otherwise
    """
    response = requests.get(plot_url)
    if response.status_code == 200:
        img = Image.open(BytesIO(response.content)).copy()
        return True, img
    else:
        return False, plot_url


@st.cache_data
def get_stac_meta(url: str):
    """
    Get the metadata from the STAC API

    Parameters
    ----------
    url: str
        The URL of the metadata to get
    Returns
    -------
    bool
        True if the metadata was successfully retrieved, False otherwise
    dict
        The metadata object if successful, the url otherwise
    """
    response = requests.get(url)
    if response.status_code == 200:
        data = json.loads(response.text)
        return True, data
    else:
        return False, url
