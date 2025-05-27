import os
import geopandas as gpd
import pandas as pd
import streamlit as st
import requests
import json
from PIL import Image
from io import BytesIO

rootDir = os.path.dirname(os.path.abspath(__file__))  # located within utils folder
srcDir = os.path.abspath(os.path.join(rootDir, ".."))  # go up one level to src
assetsDir = os.path.abspath(os.path.join(srcDir, "assets"))  # go up one level to src


def prep_gdf(gdf: gpd.GeoDataFrame, layer: str) -> gpd.GeoDataFrame:
    """
    Prepares a GeoDataFrame for plotting on a folium map.

    Parameters
    ----------
    gdf: gpd.GeoDataFrame
        A GeoDataFrame containing the map data
    layer: str
        The name of the layer

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
    return gdf


def init_pilot(pilot: str):
    """
    Initialize the map data for the selected pilot study
    """
    if pilot == "Trinity":
        st.pilot_base_url = "https://trinity-pilot.s3.amazonaws.com/stac/prod-support"
        ## TODO: Need to add local data to a STAC catalog
        st.pilot_layers = {
            "Basins": os.path.join(assetsDir, "basins.geojson"),
            "Dams": f"{st.pilot_base_url}/dams/non-usace/non-usace-dams.geojson",
            "Gages": f"{st.pilot_base_url}/gages/gages.geojson",
            "Storms": f"{st.pilot_base_url}/storms/72hr-events/storms.geojson",
            "Reference Lines": os.path.join(assetsDir, "ref_lines.geojson"),
            "Reference Points": os.path.join(assetsDir, "ref_pts.geojson"),
        }
        st.cog_layers = {
            "Bedias Creek": "s3://trinity-pilot/stac/prod-support/models/testing/bediascreek-depth-max-aug2017.cog.tif",
            "Kickapoo": "s3://trinity-pilot/stac/prod-support/models/testing/kickapoo-depth-max-aug2017.cog.tif",
            "Livingston": "s3://trinity-pilot/stac/prod-support/models/testing/livingston-depth-max-aug2017.cog.tif",
        }
    else:
        raise ValueError(f"Error: invalid pilot study {pilot}")

    df_basins = gpd.read_file(st.pilot_layers["Basins"])
    st.basins = prep_gdf(df_basins, "Basins")

    df_dams = gpd.read_file(st.pilot_layers["Dams"])
    st.dams = prep_gdf(df_dams, "Dams")

    df_gages = gpd.read_file(st.pilot_layers["Gages"]).drop_duplicates()
    st.gages = prep_gdf(df_gages, "Gages")

    df_storms = gpd.read_file(st.pilot_layers["Storms"])
    df_storms["rank"] = df_storms["rank"].astype(int)
    st.storms = prep_gdf(df_storms, "Storms")

    df_ref_lines = gpd.read_file(st.pilot_layers["Reference Lines"])
    st.ref_lines = prep_gdf(df_ref_lines, "Reference Lines")

    df_ref_points = gpd.read_file(st.pilot_layers["Reference Points"])
    st.ref_points = prep_gdf(df_ref_points, "Reference Points")


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
        img = Image.open(BytesIO(response.content))
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


@st.cache_data
def get_ref_line_ts(ref_line_id: str):
    """
    Get the time series data for a reference line

    Parameters
    ----------
    ref_line_id: str
        The ID of the reference line to get the time series data for
    Returns
    -------
    pd.DataFrame
        A DataFrame containing the time series data for the reference line
    """
    ## TODO: Need to add local data to a STAC catalog
    file_path = os.path.join(assetsDir, "ref_lines.parquet")
    ts = pd.read_parquet(
        file_path, engine="pyarrow", filters=[("id", "=", ref_line_id)]
    )
    if "time" in ts.columns:
        ts["time"] = pd.to_datetime(ts["time"])
    return ts


@st.cache_data
def get_ref_pt_ts(ref_pt_id: str):
    """
    Get the time series data for a reference point

    Parameters
    ----------
    ref_pt_id: str
        The ID of the reference point to get the time series data for
    Returns
    -------
    pd.DataFrame
        A DataFrame containing the time series data for the reference point
    """
    ## TODO: Need to add local data to a STAC catalog
    file_path = os.path.join(assetsDir, "ref_pts.parquet")
    ts = pd.read_parquet(file_path, engine="pyarrow", filters=[("id", "=", ref_pt_id)])
    if "time" in ts.columns:
        ts["time"] = pd.to_datetime(ts["time"])
    return ts
