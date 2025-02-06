import geopandas as gpd
import pandas as pd
import streamlit as st


def generate_stac_item_link(base_url, collection_id, item_id):
    return f"{st.session_state.stac_browser_url}/#/external/{base_url}/collections/{collection_id}/items/{item_id}"


@st.cache_data
def fetch_collection_data(collection_id, _progress_bar):
    items = list(
        st.session_state.stac_client.search(collections=[collection_id]).items()
    )
    item_data = []
    total_items = len(items)

    for idx, item in enumerate(items):
        stac_item_link = f"{st.session_state.stac_browser_url}/#/external/{st.session_state.stac_api_url}/collections/{collection_id}/items/{item.id}"

        event = item.properties.get("event", "N/A")
        block_group = item.properties.get("block_group", "N/A")
        realization = item.properties.get("realization", "N/A")
        SST_storm_center = item.properties.get("SST_storm_center", "N/A")
        historic_storm_date = item.properties.get("historic_storm_date", "N/A")
        historic_storm_center = item.properties.get("historic_storm_center", "N/A")
        historic_storm_season = item.properties.get("historic_storm_season", "N/A")
        historic_storm_max_precip_inches = item.properties.get(
            "historic_storm_max_precip_inches", "N/A"
        )

        item_data.append(
            {
                "ID": item.id,
                "Link": f'<a href="{stac_item_link}" target="_blank">See in Catalog</a>',
                "event": event,
                "block_group": block_group,
                "realization": realization,
                "SST_storm_center": SST_storm_center,
                "historic_storm_date": historic_storm_date,
                "historic_storm_center": historic_storm_center,
                "historic_storm_season": historic_storm_season,
                "historic_storm_max_precip_inches": historic_storm_max_precip_inches,
            }
        )
        # Update the progress bar
        _progress_bar.progress((idx + 1) / total_items)

    df = pd.DataFrame(item_data)
    return df


def collection_id(realization):
    return f"Kanawha-R{realization:02}"


@st.cache_data
def init_storm_data(storms_pq_path: str):
    st.storms = pd.read_parquet(storms_pq_path, engine="pyarrow")
    st.storms["Link"] = st.storms.apply(
        lambda row: f'<a href="{generate_stac_item_link(st.session_state.stac_api_url, collection_id(row["realization"]), row["ID"])}" target="_blank">See in Catalog</a>',
        axis=1,
    )


@st.cache_data
def init_gage_data(gages_pq_path: str):
    st.gages = pd.read_parquet(gages_pq_path, engine="pyarrow")
    st.gages["Link"] = st.gages.apply(
        lambda row: f'<a href="{generate_stac_item_link(st.session_state.stac_api_url, collection_id(row["realization"]), row["ID"])}" target="_blank">See in Catalog</a>',
        axis=1,
    )


@st.cache_data
def init_computation_data(comp_pq_path: str):
    st.computation = pd.read_parquet(comp_pq_path, engine="pyarrow")


def prep_df(df: pd.DataFrame):
    """
    Prepares a GeoDataFrame for plotting on a folium map.

    Parameters
    ----------
    df: pd.DataFrame
        A GeoDataFrame containing the map data

    Returns
    -------
    pd.DataFrame
        A GeoDataFrame with the necessary columns for plotting on a folium map
    """
    # Convert the CRS to EPSG:4326
    df = df.to_crs(epsg=4326)
    df.index.name = "id"
    df["id"] = df.index.astype(str)
    # Find the center of the map data
    centroids = df.geometry.centroid
    df["lat"] = centroids.y.astype(float)
    df["lon"] = centroids.x.astype(float)
    return df


@st.cache_data
def init_map_data(map_layer_dict: dict):
    if "Subbasins" in map_layer_dict:
        df = gpd.read_file(map_layer_dict["Subbasins"])
        st.subbasins = prep_df(df)
    if "Reaches" in map_layer_dict:
        df = gpd.read_file(map_layer_dict["Reaches"])
        st.reaches = prep_df(df)
    if "Junctions" in map_layer_dict:
        df = gpd.read_file(map_layer_dict["Junctions"])
        st.junctions = prep_df(df)
    if "Reservoirs" in map_layer_dict:
        df = gpd.read_file(map_layer_dict["Reservoirs"])
        st.reservoirs = prep_df(df)
