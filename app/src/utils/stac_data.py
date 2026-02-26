import os
import geopandas as gpd
import streamlit as st
import requests
import json
import yaml
from PIL import Image
from io import BytesIO
from db.pull import (
    query_s3_ref_points,
    query_s3_ref_lines,
    query_s3_bc_lines,
    query_s3_model_bndry,
    query_s3_geojson,
    query_s3_hms_storms,
)

rootDir = os.path.dirname(os.path.abspath(__file__))  # located within utils folder
srcDir = os.path.abspath(os.path.join(rootDir, ".."))  # go up one level to src
assetsDir = os.path.abspath(os.path.join(srcDir, "assets"))  # go up one level to src


def reset_selections():
    """
    Reset the session state.
    This is useful when switching between different features or events.
    """
    st.session_state.update(
        {
            "single_event_focus_feature_label": None,
            "single_event_focus_feature_id": None,
            "single_event_focus_lat": None,
            "single_event_focus_lon": None,
            "single_event_focus_bounding_box": None,
            "single_event_focus_feature_type": None,
            "single_event_focus_zoom": None,
            "single_event_focus_map_click": False,
            "model_id": None,
            "subbasin_id": None,
            "calibration_event": None,
            "gage_event": None,
            "ready_to_plot_ts": False,
            "cog_layer": None,
            "cog_hist": None,
            "cog_stats": None,
            "dams_filtered": None,
            "ref_points_filtered": None,
            "ref_lines_filtered": None,
            "gages_filtered": None,
            "bc_lines_filtered": None,
            "subbasins_filtered": None,
            "reaches_filtered": None,
            "junctions_filtered": None,
            "reservoirs_filtered": None,
            "stochastic_event": None,
            "stochastic_storm": None,
            "hms_element_id": None,
            "hydromet_storm_id": None,
            "storms_df_rank": None,
            "storms_df_precip": None,
            "storms_df_date": None,
            "rank_threshold": None,
            "precip_threshold": None,
            "storm_start_date": None,
            "storm_end_date": None,
            "hydromet_storm_data": None,
            "hydromet_hyetograph_data": None,
            "init_met_pilot": False,
            "storm_cache": None,
            "storm_bounds": None,
            "storm_animation_payload": None,
            "storm_animation_requested": False,
            "storm_animation_html": None,
            "storm_max": None,
            "storm_min": None,
            "hyeto_cache": {},
        }
    )


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


def init_hms_pilot(s3_conn, pilot: str):
    """
    Initialize the map data for the selected HMS pilot study

    Parameters
    ----------
    s3_conn: duckdb.DuckDBPyConnection
        The connection to the S3 account
    pilot: str
        The name of the pilot study to initialize data for
    """
    if pilot == "trinity-pilot":
        st.pilot_base_url = f"https://{pilot}.s3.amazonaws.com/stac/prod-support"
        st.pilot_layers = {
            "Dams": f"{st.pilot_base_url}/dams/non-usace/non-usace-dams.geojson",
            "Gages": f"{st.pilot_base_url}/gages/gages.geojson",
            "Subbasins": f"{st.pilot_base_url}/conformance/hydrology/trinity/assets/Subbasin.geojson",
            "Reaches": f"{st.pilot_base_url}/conformance/hydrology/trinity/assets/Reach.geojson",
            "Junctions": f"{st.pilot_base_url}/conformance/hydrology/trinity/assets/Junction.geojson",
            "Reservoirs": f"{st.pilot_base_url}/conformance/hydrology/trinity/assets/Reservoir.geojson",
        }
        st.cog_layers = {}
        st.hms_meta_url = (
            "stac-api.arc-apps.net/collections/conformance-models/items/trinity"
        )
    else:
        raise ValueError(f"Error: invalid pilot study {pilot}")

    df_dams = gpd.read_file(st.pilot_layers["Dams"])
    st.dams = prep_gdf(df_dams, "Dam")
    df_gages = gpd.read_file(st.pilot_layers["Gages"]).drop_duplicates()
    st.gages = prep_gdf(df_gages, "Gage")
    st.hms_storms = query_s3_hms_storms(s3_conn, pilot)
    df_subbasins = gpd.read_file(st.pilot_layers["Subbasins"])
    st.subbasins = prep_gdf(df_subbasins, "Subbasin", hms=True)
    st.subbasins["geometry"] = st.subbasins["geometry"].simplify(tolerance=0.001)
    df_reaches = gpd.read_file(st.pilot_layers["Reaches"])
    st.reaches = prep_gdf(df_reaches, "Reach", hms=True)
    df_junctions = gpd.read_file(st.pilot_layers["Junctions"])
    st.junctions = prep_gdf(df_junctions, "Junction", hms=True)
    df_reservoirs = gpd.read_file(st.pilot_layers["Reservoirs"])
    st.reservoirs = prep_gdf(df_reservoirs, "Reservoir", hms=True)


def _s3_to_https(s3_path: str) -> str:
    if not s3_path:
        return ""
    if not s3_path.startswith("s3://"):
        return s3_path
    path = s3_path[5:]
    if "/" in path:
        bucket, key = path.split("/", 1)
        return f"https://{bucket}.s3.amazonaws.com/{key}"
    return f"https://{path}.s3.amazonaws.com"


def _ensure_trailing_slash(path: str) -> str:
    if not path:
        return ""
    return path if path.endswith("/") else f"{path}/"


def init_met_pilot(pilot_name: str):
    """
    Initialize the map data for the selected Meteorology pilot study

    Parameters
    ----------
    pilot_name: str
        The name of the pilot study to initialize data for
    """
    cache = st.session_state.setdefault("met_pilot_cache", {})
    cached = cache.get(pilot_name)
    if cached:
        st.pilot_base_url = cached["pilot_base_url"]
        st.pilot_layers = cached["pilot_layers"]
        st.transpo = cached["transpo"]
        st.study_area = cached["study_area"]
        st.session_state["active_met_pilot"] = pilot_name
        st.session_state["pilot_bucket"] = cached.get("pilot_bucket")
        return

    config_path = os.path.join(srcDir, "configs", "projects.yaml")
    with open(config_path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    projects = data.get("projects", data)
    project_entry = None
    for entry in projects:
        if not entry:
            continue
        if entry.get("bucket") == pilot_name or entry.get("name") == pilot_name:
            project_entry = entry
            break

    if not project_entry:
        raise ValueError(f"Error: invalid pilot study {pilot_name}")

    bucket = project_entry.get("bucket") or pilot_name
    st.session_state["pilot_bucket"] = bucket
    pilot_short = bucket.split("-")[0].lower()

    storm_metadata_path = project_entry.get("storm-metadata")
    storm_collection_path = project_entry.get("storm-collection")
    study_area_path = project_entry.get("study-area-json")
    transpo_domain_path = project_entry.get("transpo-domain-json")

    st.pilot_base_url = f"https://{bucket}.s3.amazonaws.com"
    st.pilot_layers = {
        "Storms": _s3_to_https(storm_collection_path),
        "Metadata": _ensure_trailing_slash(_s3_to_https(storm_metadata_path)),
    }

    st.transpo = query_s3_geojson(
        transpo_domain_path,
        pilot_short,
    )
    st.transpo["layer"] = "Transposition Domain"
    st.study_area = query_s3_geojson(
        study_area_path,
        pilot_short,
    )
    st.study_area["layer"] = "Study Area"

    cache[pilot_name] = {
        "pilot_base_url": st.pilot_base_url,
        "pilot_layers": st.pilot_layers,
        "transpo": st.transpo,
        "study_area": st.study_area,
        "pilot_bucket": bucket,
    }
    st.session_state["active_met_pilot"] = pilot_name
    st.session_state["pilot_bucket"] = bucket


def init_ras_pilot(s3_conn, pilot: str):
    """
    Initialize the map data for the selected RAS pilot study

    Parameters
    ----------
    s3_conn: duckdb.DuckDBPyConnection
        The connection to the S3 account
    pilot: str
        The name of the pilot study to initialize data for
    """
    if pilot == "trinity-pilot":
        st.pilot_base_url = f"https://{pilot}.s3.amazonaws.com/stac/prod-support"
        st.pilot_layers = {
            "Dams": f"{st.pilot_base_url}/dams/non-usace/non-usace-dams.geojson",
            "Gages": f"{st.pilot_base_url}/gages/gages.geojson",
        }
        st.cog_layers = {}
        st.ras_meta_url = "stac-api.arc-apps.net/collections/calibration-models"
    else:
        raise ValueError(f"Error: invalid pilot study {pilot}")

    df_dams = gpd.read_file(st.pilot_layers["Dams"])
    st.dams = prep_gdf(df_dams, "Dam")
    df_gages = gpd.read_file(st.pilot_layers["Gages"]).drop_duplicates()
    st.gages = prep_gdf(df_gages, "Gage")
    st.models = query_s3_model_bndry(s3_conn, pilot, "all")
    st.models["geometry"] = st.models["geometry"].simplify(tolerance=0.001)
    st.ref_lines = query_s3_ref_lines(s3_conn, pilot, "all")
    st.ref_points = query_s3_ref_points(s3_conn, pilot, "all")
    st.bc_lines = query_s3_bc_lines(s3_conn, pilot, "all")


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
