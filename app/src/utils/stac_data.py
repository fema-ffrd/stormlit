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


def prep_df(df: pd.DataFrame, layer: str):
    """
    Prepares a GeoDataFrame for plotting on a folium map.

    Parameters
    ----------
    df: pd.DataFrame
        A GeoDataFrame containing the map data
    layer: str
        The name of the layer

    Returns
    -------
    pd.DataFrame
        A GeoDataFrame with the necessary columns for plotting on a folium map
    """
    # Get the original CRS and bbox
    crs_str = df.crs.to_string()
    bbox = df.total_bounds
    bbox_str = f"{bbox[0]:.7f},{bbox[1]:.7f},{bbox[2]:.7f},{bbox[3]:.7f}"
    # Convert the CRS to EPSG:4326
    df = df.to_crs(epsg=4326)
    # Find the center of the map data
    centroids = df.geometry.centroid
    df["lat"] = centroids.y.astype(float)
    df["lon"] = centroids.x.astype(float)
    df["layer"] = layer
    df["crs"] = crs_str
    df["bbox"] = bbox_str
    return df


@st.cache_data
def init_pilot(pilot: str):
    """ "
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
    st.basins = prep_df(df_basins, "Basins")

    df_dams = gpd.read_file(st.pilot_layers["Dams"])
    st.dams = prep_df(df_dams, "Dams")

    df_gages = gpd.read_file(st.pilot_layers["Gages"])
    st.gages = prep_df(df_gages, "Gages")

    df_storms = gpd.read_file(st.pilot_layers["Storms"])
    df_storms["rank"] = df_storms["rank"].astype(int)
    st.storms = prep_df(df_storms, "Storms")

    df_ref_lines = gpd.read_file(st.pilot_layers["Reference Lines"])
    st.ref_lines = prep_df(df_ref_lines, "Reference Lines")

    df_ref_points = gpd.read_file(st.pilot_layers["Reference Points"])
    st.ref_points = prep_df(df_ref_points, "Reference Points")


def define_gage_data(gage_id: str):
    gage_data = {
        "Metadata": f"{st.pilot_base_url}/gages/{gage_id}/{gage_id}.json",
        "Flow Stats": f"{st.pilot_base_url}/gages/{gage_id}/{gage_id}-flow-stats.png",
        "AMS": f"{st.pilot_base_url}/gages/{gage_id}/{gage_id}-ams.png",
        "AMS Seasons": f"{st.pilot_base_url}/gages/{gage_id}/{gage_id}-ams-seasonal.png",
        "AMS LP3": f"{st.pilot_base_url}/gages/{gage_id}/{gage_id}-ams-lpiii.png",
    }
    return gage_data


def define_storm_data(storm_id: str):
    storm_data = {
        "Metadata": f"{st.pilot_base_url}/storms/72hr-events/{storm_id}/{storm_id}.json",
    }
    return storm_data


def define_dam_data(dam_id: str):
    dam_data = {
        "Metadata": f"{st.pilot_base_url}/dams/non-usace/{dam_id}/{dam_id}.json",
    }
    return dam_data


@st.cache_data
def get_stac_img(plot_url: str):
    response = requests.get(plot_url)
    if response.status_code == 200:
        img = Image.open(BytesIO(response.content))
        return True, img
    else:
        return False, plot_url


@st.cache_data
def get_stac_meta(url: str):
    response = requests.get(url)
    if response.status_code == 200:
        data = json.loads(response.text)
        return True, data
    else:
        return False, url


@st.cache_data
def get_ref_line_ts(ref_line_id: str):
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
    ## TODO: Need to add local data to a STAC catalog
    file_path = os.path.join(assetsDir, "ref_pts.parquet")
    ts = pd.read_parquet(file_path, engine="pyarrow", filters=[("id", "=", ref_pt_id)])
    if "time" in ts.columns:
        ts["time"] = pd.to_datetime(ts["time"])
    return ts


# def generate_stac_item_link(base_url, collection_id, item_id):
#     return f"{st.session_state.stac_browser_url}/#/external/{base_url}/collections/{collection_id}/items/{item_id}"


# @st.cache_data
# def fetch_collection_data(collection_id, _progress_bar):
#     items = list(
#         st.session_state.stac_client.search(collections=[collection_id]).items()
#     )
#     item_data = []
#     total_items = len(items)

#     for idx, item in enumerate(items):
#         stac_item_link = f"{st.session_state.stac_browser_url}/#/external/{st.session_state.stac_api_url}/collections/{collection_id}/items/{item.id}"

#         event = item.properties.get("event", "N/A")
#         block_group = item.properties.get("block_group", "N/A")
#         realization = item.properties.get("realization", "N/A")
#         SST_storm_center = item.properties.get("SST_storm_center", "N/A")
#         historic_storm_date = item.properties.get("historic_storm_date", "N/A")
#         historic_storm_center = item.properties.get("historic_storm_center", "N/A")
#         historic_storm_season = item.properties.get("historic_storm_season", "N/A")
#         historic_storm_max_precip_inches = item.properties.get(
#             "historic_storm_max_precip_inches", "N/A"
#         )

#         item_data.append(
#             {
#                 "ID": item.id,
#                 "Link": f'<a href="{stac_item_link}" target="_blank">See in Catalog</a>',
#                 "event": event,
#                 "block_group": block_group,
#                 "realization": realization,
#                 "SST_storm_center": SST_storm_center,
#                 "historic_storm_date": historic_storm_date,
#                 "historic_storm_center": historic_storm_center,
#                 "historic_storm_season": historic_storm_season,
#                 "historic_storm_max_precip_inches": historic_storm_max_precip_inches,
#             }
#         )
#         # Update the progress bar
#         _progress_bar.progress((idx + 1) / total_items)

#     df = pd.DataFrame(item_data)
#     return df


# def collection_id(realization):
#     return f"Kanawha-R{realization:02}"


# @st.cache_data
# def init_storm_data(storms_pq_path: str):
#     st.storms = pd.read_parquet(storms_pq_path, engine="pyarrow")
#     st.storms["Link"] = st.storms.apply(
#         lambda row: f'<a href="{generate_stac_item_link(st.session_state.stac_api_url, collection_id(row["realization"]), row["ID"])}" target="_blank">See in Catalog</a>',
#         axis=1,
#     )


# @st.cache_data
# def init_gage_data(gages_pq_path: str):
#     st.gages = pd.read_parquet(gages_pq_path, engine="pyarrow")
#     st.gages["Link"] = st.gages.apply(
#         lambda row: f'<a href="{generate_stac_item_link(st.session_state.stac_api_url, collection_id(row["realization"]), row["ID"])}" target="_blank">See in Catalog</a>',
#         axis=1,
#     )


# @st.cache_data
# def init_computation_data(comp_pq_path: str):
#     st.computation = pd.read_parquet(comp_pq_path, engine="pyarrow")
