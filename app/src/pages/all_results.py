# module imports
from utils.session import init_session_state
from utils.custom import stylable_container
from utils.metrics import calc_metrics, eval_metrics, define_metrics
from utils.nwis_api import query_nwis, select_usgs_gages
from utils.mapping import get_map_pos, prep_fmap
from db.utils import create_pg_connection, create_s3_connection
from utils.plotting import (
    plot_ts,
    plot_hist,
    plot_flow_aep,
    plot_multi_event_ts,
)
from utils.stac_data import (
    init_hms_pilot,
    init_ras_pilot,
    define_gage_data,
    define_dam_data,
    get_stac_img,
    get_stac_meta,
)
from db.pull import (
    query_s3_mod_flow,
    query_s3_mod_wse,
    query_s3_mod_vel,
    query_s3_mod_stage,
    query_s3_obs_flow,
    query_s3_calibration_event_list,
    query_s3_model_thumbnail,
    query_s3_stochastic_hms_flow,
    query_s3_stochastic_storm_list,
    query_s3_stochastic_event_list,
    query_s3_ams_peaks_by_element,
    query_s3_gage_ams,
)

# standard imports
import os
import streamlit as st
import pandas as pd
import geopandas as gpd
from streamlit.errors import StreamlitDuplicateElementKey
from dotenv import load_dotenv
from streamlit_folium import st_folium
from typing import Callable, List, Optional
from urllib.parse import urljoin
from enum import Enum
import logging
from shapely.geometry import shape

currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
assetsDir = os.path.abspath(os.path.join(srcDir, "assets"))  # go up one level to src
load_dotenv()

logger = logging.getLogger(__name__)


def reset_selections():
    """
    Reset the session state for single event selections.
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
            "single_event_focus_map_click": False,
            "model_id": None,
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
        }
    )


def identify_gage_from_subbasin(subbasin_geom: gpd.GeoSeries):
    """
    Identify the gage ID from a subbasin geometry.
    Determine if there are any gage points located within the subbasin polygon

    Parameters
    ----------
    subbasin_geom: gpd.GeoSeries
        A GeoSeries containing the geometry of the subbasin.

    Returns
    -------
    gage_id: str
        The gage ID if a gage is found within the subbasin, otherwise None
    """
    # Combine all subbasin geometries into one (if multiple)
    subbasin_geom = subbasin_geom.unary_union
    # Get centroids of all gages
    gage_centroids = st.gages.centroid
    # Find which gage centroids are within the subbasin geometry
    mask = gage_centroids.within(subbasin_geom)
    filtered_gdf = st.gages[mask].copy()
    if not filtered_gdf.empty:
        return filtered_gdf["site_no"].tolist()
    else:
        return None


def identify_gage_from_pt_ln(_geom: gpd.GeoSeries):
    """
    Identify the gage ID from a point or line geometry.
    Determine if there are any gage points located within the reach line.

    Parameters
    ----------
    _geom: gpd.GeoSeries
        A GeoSeries containing the geometry of the point or line.

    Returns
    -------
    subbasin_id: str
        The subbasin ID if a subbasin is found containing the point or line, otherwise None
    """
    # Combine all geometries into one (if multiple)
    _geom = _geom.unary_union.centroid
    # Get all subbasin geometries
    subbasin_geoms = st.subbasins.geometry
    # Find which subbasins contain the ln/pt geometry
    mask = subbasin_geoms.contains(_geom)
    filtered_gdf = st.subbasins[mask].copy()
    if filtered_gdf.empty:
        return None
    else:
        return identify_gage_from_subbasin(filtered_gdf.geometry)


def identify_gage_from_ref_ln(ref_id: str):
    """
    Identify the gage ID from a reference point or line ID.

    Parameters
    ----------
    ref_id: str
        The reference ID to extract the gage ID from.

    Returns
    -------
    tuple
        A tuple containing a boolean indicating if it is a gage and the gage ID if applicable.
    """
    is_gage = False
    gage_id = None
    if "gage" in ref_id:
        is_gage = True
        ref_id = ref_id.split("_")
        # find the index where usgs appears
        for idx, part in enumerate(ref_id):
            if "usgs" in part.lower():
                gage_idx = idx + 1
                gage_id = ref_id[gage_idx]
                return is_gage, gage_id
    else:
        return is_gage, gage_id


def identify_model(geom: gpd.GeoSeries):
    """
    Identify the model that a provided geodataframe may be within.

    Parameters
    ----------
    geom: gpd.GeoSeries
        The GeoSeries containing model data.
    Returns
    -------
    model_id: str
        The model ID extracted from the GeoDataFrame.
    """
    # Get the centroids of the geometries in the GeoDataFrame
    centroid = geom.centroid
    # Check if the centroid is within any model geometry
    mask = centroid.within(st.models.geometry)
    filtered_gdf = st.models[mask].copy()
    if not filtered_gdf.empty:
        model_id = filtered_gdf.iloc[0]["model"]
        logger.debug(f"Identified model ID: {model_id}")
        return model_id


def identify_event_date(event_id: str):
    """
    Identify the event date from an event ID.

    Parameters
    ----------
    event_id: str
        The event ID to extract the event type and ID from.
        e.g. "calibration_nov2015"

    Returns
    -------
    event_date: str
        The event date extracted from the event ID.
        e.g. "nov2015"
    """
    event_date = event_id.split("_")
    if len(event_date) > 1:
        event_date = event_date[-1]
    else:
        event_date = event_id
    return event_date


class FeatureType(Enum):
    MODEL = "Model"
    GAGE = "Gage"
    DAM = "Dam"
    REFERENCE_LINE = "Reference Line"
    REFERENCE_POINT = "Reference Point"
    BC_LINE = "BC Line"
    SUBBASIN = "Subbasin"
    REACH = "Reach"
    JUNCTION = "Junction"
    RESERVOIR = "Reservoir"
    COG = "Raster Layer"
    STORM = "Storm"


def focus_feature(
    item: dict,
    item_id: str,
    item_label: str,
    feature_type: FeatureType,
    map_click: bool = False,
):
    """
    Focus on a feature by updating the session state with the item's details.

    Parameters
    ----------
    item: dict
        The item to focus on, containing its details.
    item_id: str
        The ID of the item.
    item_label: str
        The label of the item.
    feature_type: FeatureType
        The type of feature (Model, Gage, Dam, Reference Line, Reference Point, BC Line)
    map_click: bool
        Whether the focus was triggered by a map click or a button click.
    """
    logger.info("Item selected: %s", item)
    geom = item.get("geometry", None)
    if geom and isinstance(geom, dict):
        # Convert dict to Geometry object if necessary
        geom = shape(geom)
    if geom:
        bounds = geom.bounds
        bbox = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
    else:
        bbox = None

    if "model" in item:
        st.session_state["model_id"] = item["model"]
    if "hms_element" in item:
        st.session_state["hms_element_id"] = item["hms_element"]
        st.session_state["model_id"] = identify_model(geom)

    st.session_state.update(
        {
            "single_event_focus_feature_label": item_label,
            "single_event_focus_feature_id": item_id,
            "single_event_focus_lat": item.get("lat"),
            "single_event_focus_lon": item.get("lon"),
            # TODO: Add logic to determine zoom level based on item extent
            "single_event_focus_zoom": 12,
            "single_event_focus_bounding_box": bbox,
            "single_event_focus_feature_type": feature_type.value,
            "single_event_focus_map_click": map_click,
        }
    )


def map_popover(
    label: str,
    items: List[dict],
    get_item_label: Callable,
    get_item_id: Callable,
    color: str = "#f0f0f0",
    callback: Optional[Callable] = None,
    feature_type: Optional[FeatureType] = None,
    download_url: Optional[str] = None,
    image_path: Optional[str] = None,
):
    """
    Create a popover with buttons for each item in the button_data list.

    When clicked, each button will update the session state with the
    corresponding item's latitude and longitude, and zoom level.
    Parameters
    ----------
    label: str
        The label for the popover
    items: list
        A list of dictionaries containing the button data
    get_item_label: Callable
        A function that takes an item and returns the label for the button
    get_item_id: Callable
        A function that takes an item and returns the ID for the button
    callback: Optional[Callable]
        A function to be called when the button is clicked. Accepts the item as an argument.
    feature_type: Optional[FeatureType]
        The type of feature (Basin, Gage, Dam, Reference Line, Reference Point)
    download_url: Optional[str]
        A URL to download data related to the items
    image_path: Optional[str]
        A path to an image to display in the popover
    Returns
    -------
    None

    """
    with stylable_container(
        key=f"popover_container_{label}",
        css_styles=f"""
            button {{
                background-color: {color};
                color: black;
                color: black;
                border-radius: 5px;
                white-space: nowrap;
            }}
        """,
    ):
        with st.popover(label, use_container_width=True):
            if image_path:
                st.image(image_path, use_container_width=False, width=200)
            st.markdown(f"#### {label}")
            if download_url:
                st.markdown(f"⬇️ [Download Data]({download_url})")
            if len(items) == 0:
                st.write(
                    "Select a feature from the map or model from the dropdown to generate selections"
                )
            for idx, item in enumerate(items):
                item_label = get_item_label(item)
                item_id = get_item_id(item)
                current_feature_id = st.session_state.get(
                    "single_event_focus_feature_id"
                )
                if item_id == current_feature_id and item_id is not None:
                    item_label += " ✅"
                button_key = f"btn_{label}_{item_id}_{idx}"

                if label != "🌐 Raster Layers":
                    try:
                        st.button(
                            label=item_label,
                            key=button_key,
                            on_click=focus_feature,
                            args=(item, item_id, item_label, feature_type),
                        )
                    except StreamlitDuplicateElementKey as e:
                        logger.warning(
                            f"Duplicate button key detected ({button_key}): {e}.",
                        )
                        st.button(
                            label=item_label,
                            key=f"{button_key}_DUPE",
                            on_click=focus_feature,
                            args=(item, item_id, item_label, feature_type),
                            disabled=True,
                        )
                else:
                    # For COG layers, we don't want to focus on a feature, just display the label
                    try:
                        st.button(
                            label=item_label,
                            key=f"cog_{button_key}",
                            on_click=callback,
                            args=(item,),
                        )
                    except StreamlitDuplicateElementKey as e:
                        logger.warning(
                            f"Duplicate button key detected ({button_key}): {e}.",
                        )
                        st.button(
                            label=item_label,
                            key=f"cog_{button_key}_DUPE",
                            on_click=callback,
                            args=(item,),
                            disabled=True,
                        )
    st.map_output = None


def about_popover(color: str = "white"):
    """
    Render the styled About popover section.
    """
    with stylable_container(
        key="popover_container_about",
        css_styles=f"""
            button {{
                background-color: {color};
                color: black;
                border-radius: 5px;
                white-space: nowrap;
            }}
        """,
    ):
        with st.popover("READ ME ℹ️", use_container_width=True):
            st.markdown(
                """
            1. Select a pilot study to initialize the dataset.
            2. Select items from the map or dropdown.
            3. Turn map layers on and off using the layer toggle in the top right corner of the map.
            4. If selecting a model object (HEC-RAS or HEC-HMS), also select the event type and event ID:
            - **Single Event**: View deterministic results for a specific event.
                - Calibration events are historic simulations.
                - Stochastic events are synthetically generated.
            - **Multi Event**: View probabilistic results across an ensemble of stochastic events.
            5. After making a selection, statistics and analytics for that selection will be displayed to the right of the map.
            6. To reset selections, click the "Reset Selections" button located in the upper corner of the page
                """
            )


def all_results():
    st.set_page_config(page_title="stormlit", page_icon=":rain_cloud:", layout="wide")
    if "session_id" not in st.session_state:
        init_session_state()

    st.title("All Model Results")

    # Sidebar configuration
    st.sidebar.markdown("# Page Navigation")
    st.sidebar.page_link("main.py", label="Home 🏠")
    st.sidebar.page_link("pages/model_qc.py", label="Model QC")
    st.sidebar.page_link("pages/hms_results.py", label="HMS Results")
    st.sidebar.page_link("pages/ras_results.py", label="RAS Results")
    st.sidebar.page_link("pages/all_results.py", label="All Results")

    st.sidebar.markdown("## Getting Started")
    with st.sidebar:
        about_popover()

    st.sidebar.markdown("## Select Study")
    st.session_state["pilot"] = st.sidebar.selectbox(
        "Select a Pilot Study",
        [
            "trinity-pilot",
        ],
        index=0,
    )

    if st.session_state["pg_connected"] is False:
        st.session_state["pg_conn"] = create_pg_connection()
    if st.session_state["s3_connected"] is False:
        st.session_state["s3_conn"] = create_s3_connection()

    # Initialize session state variables if not already set
    if st.session_state["init_hms_pilot"] is False:
        with st.spinner("Initializing HMS datasets..."):
            init_hms_pilot(
                st.session_state["s3_conn"],
                st.session_state["pilot"],
            )
            st.session_state["init_hms_pilot"] = True
    if st.session_state["init_ras_pilot"] is False:
        with st.spinner("Initializing RAS datasets..."):
            init_ras_pilot(
                st.session_state["s3_conn"],
                st.session_state["pilot"],
            )
            st.session_state["init_ras_pilot"] = True
    dropdown_container = st.container(
        key="dropdown_container",
    )
    col_bc_lines, col_ref_points, col_ref_lines, col_models = (
        dropdown_container.columns(4)
    )
    col_subbasins, col_reaches, col_junctions, col_reservoirs = (
        dropdown_container.columns(4)
    )
    col_gages, col_dams, col_storms, reset_col = dropdown_container.columns(4)
    map_col, info_col = st.columns(2)

    with reset_col:
        if st.button("Reset Selections", type="primary", use_container_width=True):
            reset_selections()
            st.rerun()

    # Map Position
    if st.session_state["single_event_focus_feature_label"]:
        c_lat = st.session_state["single_event_focus_lat"]
        c_lon = st.session_state["single_event_focus_lon"]
        zoom = st.session_state["single_event_focus_zoom"]
    # Default map position
    else:
        c_lat, c_lon, zoom = get_map_pos(
            "RAS",
        )

    # Get the feature type from session state or default to None
    # to determine how to display the map
    feature_type = st.session_state.get("single_event_focus_feature_type")
    if feature_type is not None:
        feature_type = FeatureType(feature_type)

    # Map
    with map_col:
        with st.spinner("Loading map..."):
            st.fmap = prep_fmap(
                c_lat, c_lon, zoom, "All", st.session_state["cog_layer"]
            )
            # Fit the map to the bounding box of a selected polygon or line feature
            bbox = st.session_state.get("single_event_focus_bounding_box")
            if bbox and feature_type in [
                FeatureType.MODEL,
                FeatureType.REFERENCE_LINE,
                FeatureType.BC_LINE,
                FeatureType.SUBBASIN,
            ]:
                st.fmap.fit_bounds(bbox)
                st.map_output = st_folium(
                    st.fmap,
                    height=500,
                    use_container_width=True,
                    returned_objects=[
                        "last_active_drawing",
                    ],
                )
            elif feature_type in [
                FeatureType.GAGE,
                FeatureType.DAM,
                FeatureType.REFERENCE_POINT,
            ]:
                st.map_output = st_folium(
                    st.fmap,
                    center=[c_lat, c_lon],
                    zoom=zoom,
                    height=500,
                    use_container_width=True,
                    returned_objects=[
                        "last_active_drawing",
                    ],
                )
            else:
                st.map_output = st_folium(
                    st.fmap,
                    height=500,
                    use_container_width=True,
                    returned_objects=[
                        "last_active_drawing",
                    ],
                )
    # Handle when a feature is selected from the map
    last_active_drawing = st.map_output.get("last_active_drawing", None)
    if last_active_drawing:
        logger.debug("Map feature selected")
        properties = last_active_drawing.get("properties", {})
        layer = properties.get("layer")
        geom = last_active_drawing.get("geometry", None)
        if geom and isinstance(geom, dict):
            geom = shape(geom)
        if layer:
            feature_type = FeatureType(layer)
            if feature_type in (
                FeatureType.BC_LINE,
                FeatureType.REFERENCE_POINT,
                FeatureType.REFERENCE_LINE,
            ):
                feature_id = properties["id"]
                feature_label = feature_id
                st.session_state["model_id"] = properties["model"]
                st.session_state["hms_element_id"] = None
            elif feature_type == FeatureType.MODEL:
                feature_id = properties["model"]
                feature_label = feature_id
                st.session_state["hms_element_id"] = None
            elif feature_type in (
                FeatureType.SUBBASIN,
                FeatureType.REACH,
                FeatureType.JUNCTION,
                FeatureType.RESERVOIR,
            ):
                feature_id = properties["hms_element"]
                feature_label = feature_id
                st.session_state["model_id"] = identify_model(geom)
                st.session_state["hms_element_id"] = feature_label
            elif feature_type == FeatureType.GAGE:
                feature_id = properties["site_no"]
                feature_label = feature_id
                st.session_state["model_id"] = identify_model(geom)
                st.session_state["hms_element_id"] = None
            elif feature_type == FeatureType.DAM:
                feature_id = properties["id"]
                feature_label = feature_id
                st.session_state["model_id"] = identify_model(geom)
                st.session_state["hms_element_id"] = None
        else:
            st.warning("No layer found in map feature properties.")
    else:
        logger.debug(
            "No feature selected from map. Using session state for feature focus."
        )
        feature_id = st.session_state.get("single_event_focus_feature_id")
        feature_label = st.session_state.get("single_event_focus_feature_label")

    # Feature Info
    with info_col:
        # HEC-RAS Model Domains
        if feature_type == FeatureType.MODEL:
            st.session_state["model_id"] = feature_label
            st.markdown(f"### Model: `{feature_label}`")
            ras_stac_viewer_url = f"{st.session_state['stac_browser_url']}/#/external/{st.ras_meta_url}/items/{feature_label}"
            st.markdown(
                f"🌐 [STAC Metadata for {feature_label}]({ras_stac_viewer_url})"
            )
            model_thumbnail_img = query_s3_model_thumbnail(
                st.session_state["s3_conn"],
                st.session_state["pilot"],
                feature_label,
            )
            if model_thumbnail_img:
                st.image(
                    model_thumbnail_img,
                    caption=f"Model Thumbnail for {feature_label}",
                    use_container_width=False,
                )
            else:
                st.warning("No thumbnail available for this model.")
        # NID Dams
        elif feature_type == FeatureType.DAM:
            info_col.markdown(f"### Model: `{st.session_state['model_id']}`")
            info_col.markdown(f"#### Dam: `{feature_label}`")
            dam_data = define_dam_data(feature_id)
            dam_meta_url = dam_data["Metadata"]
            dam_meta_status_ok, dam_meta = get_stac_meta(dam_meta_url)
            if dam_meta_status_ok:
                dam_stac_viewer_url = (
                    f"{st.session_state['stac_browser_url']}/#/external/{dam_meta_url}"
                )
                st.markdown(
                    f"🌐 [STAC Metadata for Dam {feature_id}]({dam_stac_viewer_url})"
                )

                st.markdown("#### Documentation")
                for asset_name, asset in dam_meta["assets"].items():
                    roles = asset.get("roles", [])
                    asset_href = asset.get("href")
                    asset_url = urljoin(dam_meta_url, asset_href)
                    if "document" in roles:
                        st.markdown(f"📄 [{asset_name}]({asset_url})")
                    elif "spreadsheet" in roles:
                        st.markdown(f"📊 [{asset_name}]({asset_url})")
        # USGS Gages
        elif feature_type == FeatureType.GAGE:
            info_col.markdown(f"### Model: `{st.session_state['model_id']}`")
            info_col.markdown(f"#### Gage: `{feature_label}`")
            gage_data = define_gage_data(feature_id)
            gage_meta_url = gage_data["Metadata"]
            gage_meta_status_ok, gage_meta = get_stac_meta(gage_meta_url)
            if gage_meta_status_ok:
                gage_stac_viewer_url = (
                    f"{st.session_state['stac_browser_url']}/#/external/{gage_meta_url}"
                )
                gage_props = gage_meta.get("properties", {})
                st.markdown(f"""
                            * **Station Name:** {gage_props.get("station_nm")}
                            * **Site No:** `{gage_props.get("site_no")}`
                            * **HUC:** `{gage_props.get("huc_cd")}`
                            * **Drainage Area:** {gage_props.get("drain_area_va")}
                            """)
                st.markdown(
                    f"🌐 [STAC Metadata for Gage {feature_id}]({gage_stac_viewer_url})"
                )
            st.markdown("#### Gage Analytics 📊")
            for plot_type, plot_url in gage_data.items():
                if plot_type != "Metadata":
                    with st.expander(plot_type, expanded=False):
                        # st.markdown(f"##### {plot_type}")
                        plot_status_ok, plot_img = get_stac_img(plot_url)
                        if plot_status_ok:
                            st.image(plot_img, use_container_width=True)
                        else:
                            st.error(f"Error retrieving {plot_type} image.")
        # HEC-RAS Model Objects
        elif feature_type in [
            FeatureType.BC_LINE,
            FeatureType.REFERENCE_POINT,
            FeatureType.REFERENCE_LINE,
        ]:
            st.markdown(f"### Model: `{st.session_state['model_id']}`")
            st.markdown(f"#### {feature_type.value}: `{feature_label}`")
            ras_stac_viewer_url = f"{st.session_state['stac_browser_url']}/#/external/{st.ras_meta_url}/items/{st.session_state['model_id']}"
            st.markdown(
                f"🌐 [STAC Metadata for {st.session_state['model_id']}]({ras_stac_viewer_url})"
            )
            st.markdown("#### Select Event")
            (
                col_event_type,
                col_event_id,
            ) = info_col.columns(2)
            st.session_state["event_type"] = col_event_type.radio(
                "Select from",
                ["Calibration Events", "Stochastic Events", "Multi Events"],
                index=0,
            )
            if st.session_state["event_type"] == "Calibration Events":
                if st.session_state["model_id"] is None:
                    st.warning(
                        "Please select a model object from the map or drop down list"
                    )
                else:
                    calibration_events = query_s3_calibration_event_list(
                        st.session_state["s3_conn"],
                        st.session_state["pilot"],
                        st.session_state["model_id"],
                    )
                    if len(calibration_events) > 0:
                        st.session_state["calibration_event"] = col_event_id.selectbox(
                            "Select from",
                            calibration_events,
                            index=None,
                        )
                    else:
                        st.warning("No calibration events found for this model.")
                        st.session_state["calibration_event"] = None
                    if st.session_state["calibration_event"] is None:
                        st.warning(
                            "Please select a calibration event to view time series data."
                        )
                    else:
                        st.session_state["ready_to_plot_ts"] = True
                        st.session_state["gage_event"] = identify_event_date(
                            st.session_state["calibration_event"]
                        )
            else:
                st.write("Coming soon...")
                st.session_state["ready_to_plot_ts"] = False
                st.session_state["calibration_event"] = None
            if (
                st.session_state["ready_to_plot_ts"] is True
                and st.session_state["calibration_event"] is not None
            ):
                # Reference Point
                if feature_type == FeatureType.REFERENCE_POINT:
                    ref_pt_wse_ts = query_s3_mod_wse(
                        st.session_state["s3_conn"],
                        st.session_state["pilot"],
                        feature_label,
                        "ref_point",
                        st.session_state["calibration_event"],
                        st.session_state["model_id"],
                    )
                    ref_pt_vel_ts = query_s3_mod_vel(
                        st.session_state["s3_conn"],
                        st.session_state["pilot"],
                        feature_label,
                        "ref_point",
                        st.session_state["calibration_event"],
                        st.session_state["model_id"],
                    )
                    ref_pt_ts = ref_pt_wse_ts.merge(
                        ref_pt_vel_ts, on="time", how="outer"
                    )
                    info_col.markdown("### Modeled WSE & Velocity")
                    with info_col.expander("Plots", expanded=False, icon="📈"):
                        plot_ts(
                            ref_pt_wse_ts,
                            ref_pt_vel_ts,
                            "wse",
                            "velocity",
                            dual_y_axis=True,
                            plot_title=feature_label,
                            y_axis01_title="Velocity (ft/s)",
                            y_axis02_title="WSE (ft)",
                        )
                    with info_col.expander("Tables", expanded=False, icon="🔢"):
                        st.dataframe(ref_pt_ts.drop(columns=["id_x", "id_y"]))
                # Boundary Condition Line
                elif feature_type == FeatureType.BC_LINE:
                    bc_line_flow_ts = query_s3_mod_flow(
                        st.session_state["s3_conn"],
                        st.session_state["pilot"],
                        feature_label,
                        "bc_line",
                        st.session_state["calibration_event"],
                        st.session_state["model_id"],
                    )
                    bc_line_stage_ts = query_s3_mod_stage(
                        st.session_state["s3_conn"],
                        st.session_state["pilot"],
                        feature_label,
                        "bc_line",
                        st.session_state["calibration_event"],
                        st.session_state["model_id"],
                    )
                    bc_line_ts = bc_line_flow_ts.merge(
                        bc_line_stage_ts, on="time", how="outer"
                    )
                    info_col.markdown("### Modeled Flow & WSE")
                    with info_col.expander("Plots", expanded=True, icon="📈"):
                        plot_ts(
                            bc_line_flow_ts,
                            bc_line_stage_ts,
                            "flow",
                            "stage",
                            dual_y_axis=True,
                            plot_title=feature_label,
                            y_axis01_title="WSE (ft)",
                            y_axis02_title="Flow (cfs)",
                        )
                    with info_col.expander("Tables", expanded=False, icon="🔢"):
                        st.dataframe(bc_line_ts.drop(columns=["id_x", "id_y"]))
                # Reference Line
                if feature_type == FeatureType.REFERENCE_LINE:
                    gage_flow_ts = None
                    gage_stage_ts = None
                    feature_gage_status, feature_gage_id = identify_gage_from_ref_ln(
                        feature_label
                    )
                    ref_line_flow_ts = query_s3_mod_flow(
                        st.session_state["s3_conn"],
                        st.session_state["pilot"],
                        feature_label,
                        "ref_line",
                        st.session_state["calibration_event"],
                        st.session_state["model_id"],
                    )
                    ref_line_flow_ts.rename(
                        columns={"flow": "model_flow"}, inplace=True
                    )
                    ref_line_wse_ts = query_s3_mod_wse(
                        st.session_state["s3_conn"],
                        st.session_state["pilot"],
                        feature_label,
                        "ref_line",
                        st.session_state["calibration_event"],
                        st.session_state["model_id"],
                    )
                    ref_line_wse_ts.rename(columns={"wse": "model_wse"}, inplace=True)
                    ref_line_ts = ref_line_flow_ts.merge(
                        ref_line_wse_ts, on="time", how="outer"
                    )
                    if feature_gage_status:
                        # Gage Comparisons against Modeled Flow and Stage
                        # Get the gage datum from the NWIS
                        gage_metadata = select_usgs_gages(
                            site_code=[feature_gage_id],
                            parameter="Streamflow",
                        )
                        if "alt_va" in gage_metadata.columns:
                            gage_datum = gage_metadata["alt_va"].iloc[0]
                        else:
                            gage_datum = 0.0
                        # Set the start and end times for the event window
                        start_date = ref_line_ts["time"].min().strftime("%Y-%m-%d")
                        end_date = ref_line_ts["time"].max().strftime("%Y-%m-%d")
                        # Get the WSE Data
                        gage_stage_ts = query_nwis(
                            site=feature_gage_id,
                            parameter="Stage",
                            start_date=start_date,
                            end_date=end_date,
                            data_type="iv",
                            reference_df=ref_line_wse_ts,
                        )
                        if gage_stage_ts.empty:
                            gage_stage_ts = pd.DataFrame(columns=["time", "obs_wse"])

                        # Get the Flow Data
                        obs_flow_ts = query_s3_obs_flow(
                            st.session_state["s3_conn"],
                            st.session_state["pilot"],
                            feature_gage_id,
                            st.session_state["gage_event"],
                        )
                        if obs_flow_ts.empty:
                            # try getting instantaneous values from the NWIS
                            gage_flow_ts = query_nwis(
                                site=feature_gage_id,
                                parameter="Streamflow",
                                start_date=start_date,
                                end_date=end_date,
                                data_type="iv",
                                reference_df=ref_line_flow_ts,
                            )
                        else:
                            gage_flow_ts = obs_flow_ts.merge(
                                ref_line_flow_ts, on="time", how="outer"
                            )
                        info_col.markdown("### Observed vs Modeled Flow")
                        with info_col.expander(
                            "Plots",
                            expanded=False,
                            icon="📈",
                        ):
                            plot_ts(
                                gage_flow_ts,
                                ref_line_flow_ts,
                                "obs_flow",
                                "model_flow",
                                dual_y_axis=False,
                                plot_title=feature_label,
                                y_axis01_title="Discharge (cfs)",
                            )
                        if feature_gage_status:
                            with info_col.expander(
                                "Metrics",
                                expanded=False,
                                icon="📊",
                            ):
                                if not gage_flow_ts.empty:
                                    gage_flow_metrics = calc_metrics(
                                        gage_flow_ts, "flow"
                                    )
                                    eval_flow_df = eval_metrics(gage_flow_metrics)
                                    st.markdown("#### Calibration Metrics")
                                    st.dataframe(eval_flow_df, use_container_width=True)
                                    define_metrics()
                        with info_col.expander("Tables", expanded=False, icon="🔢"):
                            if not gage_flow_ts.empty:
                                st.markdown("#### Gage Flow Data")
                                st.dataframe(gage_flow_ts)
                            else:
                                st.markdown("#### Reference Line Flow Data")
                                st.dataframe(ref_line_flow_ts)

                        info_col.markdown("### Observed vs Modeled WSE")
                        if feature_gage_status and not gage_stage_ts.empty:
                            col_gage_datum1, col_gage_datum2 = st.columns(2)
                            col_gage_datum1.metric(
                                "USGS Gage Datum",
                                f"{gage_datum:.2f} ft",
                                delta=None,
                            )
                            st.session_state["gage_datum"] = (
                                col_gage_datum2.number_input(
                                    "Manual Override",
                                    value=gage_datum,
                                    step=0.01,
                                    format="%.2f",
                                    help="The gage datum is the elevation of the gage above sea level.",
                                )
                            )
                            gage_stage_ts["obs_wse"] = (
                                gage_stage_ts["obs_stage"]
                                + st.session_state["gage_datum"]
                            )
                        with info_col.expander("Plots", expanded=False, icon="📈"):
                            plot_ts(
                                gage_stage_ts,
                                ref_line_wse_ts,
                                "obs_wse",
                                "model_wse",
                                dual_y_axis=False,
                                plot_title=feature_label,
                                y_axis01_title="WSE (ft)",
                            )
                        if feature_gage_status:
                            with info_col.expander(
                                "Metrics",
                                expanded=False,
                                icon="📊",
                            ):
                                if not gage_stage_ts.empty:
                                    gage_wse_metrics = calc_metrics(
                                        gage_stage_ts, "wse"
                                    )
                                    eval_wse_df = eval_metrics(gage_wse_metrics)
                                    st.markdown("#### Calibration Metrics")
                                    st.dataframe(eval_wse_df, use_container_width=True)
                                    define_metrics()
                        with info_col.expander("Tables", expanded=False, icon="🔢"):
                            if not gage_stage_ts.empty:
                                st.markdown("#### Gage WSE Data")
                                st.dataframe(gage_stage_ts)
                            else:
                                st.markdown("#### Reference Line WSE Data")
                                st.dataframe(ref_line_wse_ts)
                    else:
                        # No Gage Comparisons, only Modeled Flow and Stage
                        info_col.markdown("### Modeled Flow & WSE")
                        with info_col.expander(
                            "Plots",
                            expanded=False,
                            icon="📈",
                        ):
                            plot_ts(
                                ref_line_flow_ts,
                                ref_line_wse_ts,
                                "model_flow",
                                "model_wse",
                                dual_y_axis=True,
                                plot_title=feature_label,
                                y_axis01_title="WSE (ft)",
                                y_axis02_title="Discharge (cfs)",
                            )
                        with info_col.expander("Tables", expanded=False, icon="🔢"):
                            st.markdown("#### Reference Line Flow Data")
                            st.dataframe(ref_line_flow_ts)
                            st.markdown("#### Reference Line WSE Data")
                            st.dataframe(ref_line_wse_ts)
        # HEC-HMS Model Objects
        elif feature_type in [
            FeatureType.SUBBASIN,
            FeatureType.REACH,
            FeatureType.JUNCTION,
            FeatureType.RESERVOIR,
        ]:
            st.markdown(f"### Model: `{st.session_state['model_id']}`")
            st.markdown(f"#### {feature_type.value}: `{feature_label}`")
            hms_stac_viewer_url = (
                f"{st.session_state['stac_browser_url']}/#/external/{st.hms_meta_url}"
            )
            st.markdown(
                f"🌐 [STAC Metadata for {feature_label}]({hms_stac_viewer_url})"
            )
            st.markdown("#### Select Event")
            col_event_type, col_storm_id, col_event_id = info_col.columns(3)
            st.session_state["event_type"] = col_event_type.radio(
                "Select from",
                ["Calibration Events", "Stochastic Events", "Multi Events"],
                index=0,
            )
            if feature_type == FeatureType.SUBBASIN:
                available_gage_ids = identify_gage_from_subbasin(
                    st.subbasins.loc[st.subbasins["hms_element"] == feature_label][
                        "geometry"
                    ]
                )
            elif feature_type == FeatureType.REACH:
                available_gage_ids = identify_gage_from_pt_ln(
                    st.reaches.loc[st.reaches["hms_element"] == feature_label][
                        "geometry"
                    ]
                )
            elif feature_type == FeatureType.JUNCTION:
                available_gage_ids = identify_gage_from_pt_ln(
                    st.junctions.loc[st.junctions["hms_element"] == feature_label][
                        "geometry"
                    ]
                )
            elif feature_type == FeatureType.RESERVOIR:
                available_gage_ids = identify_gage_from_pt_ln(
                    st.reservoirs.loc[st.reservoirs["hms_element"] == feature_label][
                        "geometry"
                    ]
                )
            else:
                available_gage_ids = None

            if st.session_state["event_type"] == "Stochastic Events":
                if st.session_state["hms_element_id"] is None:
                    st.warning(
                        "Please select a HEC-HMS model object from the map or drop down list"
                    )
                else:
                    stochastic_storms = query_s3_stochastic_storm_list(
                        st.session_state["s3_conn"], st.session_state["pilot"]
                    )
                    st.session_state["stochastic_storm"] = col_storm_id.selectbox(
                        "Select Storm ID",
                        sorted(stochastic_storms),
                        index=None,
                    )
                    if st.session_state["stochastic_storm"] is None:
                        st.warning("Please select a stochastic storm.")
                    else:
                        stochastic_events = query_s3_stochastic_event_list(
                            st.session_state["s3_conn"],
                            st.session_state["pilot"],
                            st.session_state["hms_element_id"],
                            st.session_state["stochastic_storm"],
                        )
                        st.session_state["stochastic_event"] = col_event_id.selectbox(
                            "Select Event ID",
                            sorted(stochastic_events),
                            index=None,
                        )
                        if st.session_state["stochastic_event"] is None:
                            st.warning("Please select a stochastic event.")
                if (
                    st.session_state["stochastic_event"] is not None
                    and st.session_state["stochastic_storm"] is not None
                ):
                    stochastic_flow_ts = query_s3_stochastic_hms_flow(
                        st.session_state["s3_conn"],
                        st.session_state["pilot"],
                        st.session_state["hms_element_id"],
                        st.session_state["stochastic_storm"],
                        st.session_state["stochastic_event"],
                    )
                    info_col.markdown("### Modeled Flow")
                    with info_col.expander("Plots", expanded=False, icon="📈"):
                        plot_ts(
                            stochastic_flow_ts,
                            pd.DataFrame(),
                            "hms_flow",
                            "flow",
                            title=feature_label,
                            dual_y_axis=False,
                        )
                    with info_col.expander("Tables", expanded=False, icon="🔢"):
                        st.dataframe(stochastic_flow_ts)
            elif st.session_state["event_type"] == "Multi Events":
                if st.session_state["hms_element_id"] is None:
                    st.warning(
                        "Please select a HEC-HMS model object from the map or drop down list"
                    )
                else:
                    if available_gage_ids is not None:
                        st.session_state["multi_event_gage_id"] = (
                            col_storm_id.selectbox(
                                "Select Gage ID",
                                available_gage_ids,
                                index=0,
                            )
                        )
                    else:
                        col_storm_id.warning(
                            "The selected HEC-HMS element is not associated with any gages."
                        )
                        gage_ams_df = None
                        st.session_state["multi_event_gage_id"] = None

                    multi_event_ams_df = query_s3_ams_peaks_by_element(
                        st.session_state["s3_conn"],
                        st.session_state["pilot"],
                        st.session_state["hms_element_id"],
                        realization_id=1,
                    )
                    multi_event_ams_df["aep"] = multi_event_ams_df["rank"] / (
                        len(multi_event_ams_df)
                    )
                    multi_event_ams_df["return_period"] = 1 / multi_event_ams_df["aep"]
                    multi_event_ams_df = pd.merge(
                        multi_event_ams_df,
                        st.hms_storms,
                        left_on="event_id",
                        right_on="event_id",
                        how="left",
                    )
                    multi_event_ams_df["storm_id"] = pd.to_datetime(
                        multi_event_ams_df["storm_id"]
                    ).dt.strftime("%Y-%m-%d")

                    if st.session_state["multi_event_gage_id"] is not None:
                        gage_ams_df = query_s3_gage_ams(
                            st.session_state["s3_conn"],
                            st.session_state["pilot"],
                            st.session_state["multi_event_gage_id"],
                        )
                        gage_ams_df["aep"] = gage_ams_df["rank"] / (len(gage_ams_df))
                        gage_ams_df["return_period"] = 1 / gage_ams_df["aep"]
                        gage_ams_df["peak_time"] = pd.to_datetime(
                            gage_ams_df["peak_time"]
                        ).dt.strftime("%Y-%m-%d")
                    else:
                        gage_ams_df = None
                    with info_col.expander("Plots", expanded=True, icon="📈"):
                        st.write(
                            "Select one or multiple points (hold shift) from the curve to view their full hydrograph time series."
                        )
                        selected_points = plot_flow_aep(multi_event_ams_df, gage_ams_df)
                        multi_events_flows_df = None
                        multi_events_baseflows_df = None
                        if selected_points:
                            multi_events_flows = []
                            multi_events_baseflows = []
                            for point in selected_points:
                                if "gage_id" in selected_points[point]:
                                    gage_flow_ts = query_s3_obs_flow(
                                        st.session_state["s3_conn"],
                                        st.session_state["pilot"],
                                        selected_points[point]["gage_id"],
                                        selected_points[point]["storm_id"],
                                    )
                                    if not gage_flow_ts.empty:
                                        gage_flow_ts["block_id"] = point
                                        gage_flow_ts["storm_id"] = selected_points[
                                            point
                                        ]["storm_id"]
                                        gage_flow_ts["event_id"] = selected_points[
                                            point
                                        ]["event_id"]
                                        multi_events_flows.append(gage_flow_ts)
                                    else:
                                        peak_time = selected_points[point]["peak_time"]
                                        peak_time_dt = pd.to_datetime(
                                            peak_time,
                                            format="%Y-%m-%d",
                                            errors="coerce",
                                        )
                                        start_date = (
                                            peak_time_dt - pd.Timedelta(days=1)
                                        ).strftime("%Y-%m-%d")
                                        end_date = (
                                            peak_time_dt + pd.Timedelta(days=1)
                                        ).strftime("%Y-%m-%d")
                                        # try getting instantaneous values from the NWIS
                                        gage_flow_ts = query_nwis(
                                            site=selected_points[point]["gage_id"],
                                            parameter="Streamflow",
                                            start_date=start_date,
                                            end_date=end_date,
                                            data_type="iv",
                                            reference_df=pd.DataFrame(),
                                        )
                                        if not gage_flow_ts.empty:
                                            gage_flow_ts["block_id"] = point
                                            gage_flow_ts["storm_id"] = selected_points[
                                                point
                                            ]["storm_id"]
                                            gage_flow_ts["event_id"] = selected_points[
                                                point
                                            ]["event_id"]
                                            multi_events_flows.append(gage_flow_ts)
                                else:
                                    # Get the Stochastic Hydrographs
                                    stochastic_flow_ts = query_s3_stochastic_hms_flow(
                                        st.session_state["s3_conn"],
                                        st.session_state["pilot"],
                                        st.session_state["hms_element_id"],
                                        selected_points[point]["storm_id"],
                                        selected_points[point]["event_id"],
                                        flow_type="FLOW",
                                    )
                                    stochastic_flow_ts["block_id"] = point
                                    stochastic_flow_ts["storm_id"] = selected_points[
                                        point
                                    ]["storm_id"]
                                    stochastic_flow_ts["event_id"] = selected_points[
                                        point
                                    ]["event_id"]
                                    multi_events_flows.append(stochastic_flow_ts)
                                    # Get the Stochastic Baseflows
                                    stochastic_baseflow_ts = (
                                        query_s3_stochastic_hms_flow(
                                            st.session_state["s3_conn"],
                                            st.session_state["pilot"],
                                            st.session_state["hms_element_id"],
                                            selected_points[point]["storm_id"],
                                            selected_points[point]["event_id"],
                                            flow_type="FLOW-BASE",
                                        )
                                    )
                                    stochastic_baseflow_ts["block_id"] = point
                                    stochastic_baseflow_ts["storm_id"] = (
                                        selected_points[point]["storm_id"]
                                    )
                                    stochastic_baseflow_ts["event_id"] = (
                                        selected_points[point]["event_id"]
                                    )
                                    multi_events_flows.append(stochastic_flow_ts)
                                    multi_events_baseflows.append(
                                        stochastic_baseflow_ts
                                    )
                            if len(multi_events_flows) > 0:
                                multi_events_flows_df = pd.concat(
                                    multi_events_flows,
                                    ignore_index=False,
                                )
                            if len(multi_events_baseflows) > 0:
                                multi_events_baseflows_df = pd.concat(
                                    multi_events_baseflows,
                                    ignore_index=False,
                                )
                            if (
                                multi_events_flows_df is not None
                                and multi_events_baseflows_df is None
                            ):
                                plot_multi_event_ts(
                                    multi_events_flows_df, pd.DataFrame()
                                )
                            elif (
                                multi_events_flows_df is not None
                                and multi_events_baseflows_df is not None
                            ):
                                plot_multi_event_ts(
                                    multi_events_flows_df, multi_events_baseflows_df
                                )

                    with info_col.expander("Tables", expanded=False, icon="🔢"):
                        st.markdown("#### Multi Event AMS Data")
                        st.dataframe(multi_event_ams_df)
                        if gage_ams_df is not None:
                            st.markdown("#### Gage AMS Data")
                            st.dataframe(gage_ams_df)
                        if multi_events_flows_df is not None:
                            st.markdown("#### Multi Event Hydrographs")
                            st.dataframe(multi_events_flows_df)
                        if multi_events_baseflows_df is not None:
                            st.markdown("#### Multi Event Baseflows")
                            st.dataframe(multi_events_baseflows_df)
            else:
                st.write("Coming soon...")
                st.session_state["stochastic_event"] = None
                st.session_state["stochastic_storm"] = None
        # Raster Layer
        elif feature_type == FeatureType.COG:
            st.markdown(f"### Raster Layer: `{st.session_state['cog_layer']}`")
            with st.expander("Statistics", expanded=True, icon="📊"):
                # plot a histogram of the COG
                hist_df = pd.DataFrame(st.session_state["cog_hist"]).T
                if hist_df.empty:
                    st.warning("No histogram data available for this COG layer.")
                else:
                    hist_df.columns = ["Count", "Value"]
                    st.session_state["cog_hist_nbins"] = st.slider(
                        "Select number of bins for histogram",
                        min_value=5,
                        max_value=100,
                        value=20,
                    )
                    hist_fig = plot_hist(
                        hist_df,
                        x_col="Value",
                        y_col="Count",
                        nbins=st.session_state["cog_hist_nbins"],
                    )
                    st.plotly_chart(hist_fig, use_container_width=True)
                    st.write(st.session_state["cog_stats"])
        else:
            st.markdown(
                """
                ### Begin by selecting a feature from the map or dropdown.
            1. **Map**: select any feature to generate selections based on that feature's geometry.
            2.  **Dropdown**: select a HEC-RAS model to generate additional selections within the other 
            dropdowns that are then filtered to be within that model.
                """
            )

    with dropdown_container:
        if st.session_state["model_id"] is None:
            # Default stats for entire pilot study
            num_dams = len(st.dams)
            num_ref_points = len(st.ref_points)
            num_ref_lines = len(st.ref_lines)
            num_gages = len(st.gages)
            num_models = len(st.models)
            num_bc_lines = len(st.bc_lines)
            num_subbasins = len(st.subbasins)
            num_reaches = len(st.reaches)
            num_junctions = len(st.junctions)
            num_reservoirs = len(st.reservoirs)
        else:
            # BC Lines
            st.session_state["bc_lines_filtered"] = st.bc_lines[
                st.bc_lines["model"] == st.session_state["model_id"]
            ]

            # Reference Points
            st.session_state["ref_points_filtered"] = st.ref_points[
                st.ref_points["model"] == st.session_state["model_id"]
            ]
            num_ref_points = len(st.session_state["ref_points_filtered"])
            # Reference Lines
            st.session_state["ref_lines_filtered"] = st.ref_lines[
                st.ref_lines["model"] == st.session_state["model_id"]
            ]
            num_ref_lines = len(st.session_state["ref_lines_filtered"])
            # Models
            num_models = 1
            selected_model = st.models[
                st.models["model"] == st.session_state["model_id"]
            ]
            num_bc_lines = len(st.session_state["bc_lines_filtered"])
            # Subbasins
            if not selected_model.empty:
                model_geom = selected_model.geometry.iloc[0]
                centroids = st.subbasins.geometry.centroid
                mask = centroids.within(model_geom)
                st.session_state["subbasins_filtered"] = st.subbasins[mask].copy()
                st.session_state["subbasins_filtered"]["model"] = st.session_state[
                    "model_id"
                ]
                num_subbasins = len(st.session_state["subbasins_filtered"])
            else:
                st.session_state["subbasins_filtered"] = None
                num_subbasins = 0
            num_subbasins = len(st.session_state["subbasins_filtered"])
            # Reaches
            if not selected_model.empty:
                model_geom = selected_model.geometry.iloc[0]
                centroids = st.reaches.geometry.centroid
                mask = centroids.within(model_geom)
                st.session_state["reaches_filtered"] = st.reaches[mask].copy()
                st.session_state["reaches_filtered"]["model"] = st.session_state[
                    "model_id"
                ]
            else:
                st.session_state["reaches_filtered"] = None
                num_reaches = 0
            num_reaches = len(st.session_state["reaches_filtered"])
            # Junctions
            if not selected_model.empty:
                model_geom = selected_model.geometry.iloc[0]
                centroids = st.junctions.geometry.centroid
                mask = centroids.within(model_geom)
                st.session_state["junctions_filtered"] = st.junctions[mask].copy()
                st.session_state["junctions_filtered"]["model"] = st.session_state[
                    "model_id"
                ]
            else:
                st.session_state["junctions_filtered"] = None
                num_junctions = 0
            num_junctions = len(st.session_state["junctions_filtered"])
            # Reservoirs
            if not selected_model.empty:
                model_geom = selected_model.geometry.iloc[0]
                centroids = st.reservoirs.geometry.centroid
                mask = centroids.within(model_geom)
                st.session_state["reservoirs_filtered"] = st.reservoirs[mask].copy()
                st.session_state["reservoirs_filtered"]["model"] = st.session_state[
                    "model_id"
                ]
            else:
                st.session_state["reservoirs_filtered"] = None
                num_reservoirs = 0
            num_reservoirs = len(st.session_state["reservoirs_filtered"])
            # Gages
            st.session_state["gages_filtered"] = gpd.sjoin(
                st.gages,
                st.models[st.models["model"] == st.session_state["model_id"]],
                how="inner",
                predicate="intersects",
            )
            st.session_state["gages_filtered"]["lat"] = st.session_state[
                "gages_filtered"
            ]["lat_left"]
            st.session_state["gages_filtered"]["lon"] = st.session_state[
                "gages_filtered"
            ]["lon_left"]
            st.session_state["gages_filtered"]["index"] = st.session_state[
                "gages_filtered"
            ]["index_right"]
            st.session_state["gages_filtered"]["layer"] = "Gages"
            st.session_state["gages_filtered"].drop(
                columns=[
                    "lat_left",
                    "lon_left",
                    "lat_right",
                    "lon_right",
                    "layer_right",
                    "layer_left",
                    "index_right",
                ],
                inplace=True,
            )
            num_gages = len(st.session_state["gages_filtered"])
            # Dams
            st.session_state["dams_filtered"] = gpd.sjoin(
                st.dams,
                st.models[st.models["model"] == st.session_state["model_id"]],
                how="inner",
                predicate="intersects",
            )
            st.session_state["dams_filtered"]["lat"] = st.session_state[
                "dams_filtered"
            ]["lat_left"]
            st.session_state["dams_filtered"]["lon"] = st.session_state[
                "dams_filtered"
            ]["lon_left"]
            st.session_state["dams_filtered"]["index"] = st.session_state[
                "dams_filtered"
            ]["index_right"]
            st.session_state["dams_filtered"]["layer"] = "Dams"
            st.session_state["dams_filtered"].drop(
                columns=[
                    "lat_left",
                    "lon_left",
                    "lat_right",
                    "lon_right",
                    "layer_right",
                    "layer_left",
                    "index_right",
                ],
                inplace=True,
            )
            num_dams = len(st.session_state["dams_filtered"])

    # Dropdowns for each feature type
    with col_bc_lines:
        map_popover(
            "🟥BC Lines (HEC-RAS)",
            {}
            if st.session_state["bc_lines_filtered"] is None
            else st.session_state["bc_lines_filtered"].to_dict("records"),
            lambda bc_line: bc_line["id"],
            get_item_id=lambda bc_line: bc_line["id"],
            feature_type=FeatureType.BC_LINE,
            image_path=os.path.join(assetsDir, "bc_line_icon.jpg"),
        )
    with col_ref_points:
        map_popover(
            "🟧 Reference Points (HEC-RAS)",
            {}
            if st.session_state["ref_points_filtered"] is None
            else st.session_state["ref_points_filtered"].to_dict("records"),
            lambda ref_point: ref_point["id"],
            get_item_id=lambda ref_point: ref_point["id"],
            feature_type=FeatureType.REFERENCE_POINT,
            image_path=os.path.join(assetsDir, "ref_point_icon.png"),
        )
    with col_ref_lines:
        map_popover(
            "🟨 Reference Lines (HEC-RAS)",
            {}
            if st.session_state["ref_lines_filtered"] is None
            else st.session_state["ref_lines_filtered"].to_dict("records"),
            lambda ref_line: ref_line["id"],
            get_item_id=lambda ref_line: ref_line["id"],
            feature_type=FeatureType.REFERENCE_LINE,
            image_path=os.path.join(assetsDir, "ref_line_icon.png"),
        )
    with col_models:
        map_popover(
            "🟩 Models (HEC-RAS)",
            st.models.to_dict("records"),
            lambda model: f"{model['model']}",
            get_item_id=lambda model: model["model"],
            feature_type=FeatureType.MODEL,
            image_path=os.path.join(assetsDir, "model_icon.jpg"),
        )
    with col_subbasins:
        map_popover(
            "🟦 Subbasins (HEC-HMS)",
            {}
            if st.session_state["subbasins_filtered"] is None
            else st.session_state["subbasins_filtered"].to_dict("records"),
            lambda subbasin: subbasin["hms_element"],
            get_item_id=lambda subbasin: subbasin["hms_element"],
            feature_type=FeatureType.SUBBASIN,
            image_path=os.path.join(assetsDir, "subbasins_icon.png"),
        )
    with col_reaches:
        map_popover(
            "🟪 Reaches (HEC-HMS)",
            {}
            if st.session_state["reaches_filtered"] is None
            else st.session_state["reaches_filtered"].to_dict("records"),
            lambda reach: reach["hms_element"],
            get_item_id=lambda reach: reach["hms_element"],
            feature_type=FeatureType.REACH,
            image_path=os.path.join(assetsDir, "reaches_icon.png"),
        )
    with col_junctions:
        map_popover(
            "🟫 Junctions (HEC-HMS)",
            {}
            if st.session_state["junctions_filtered"] is None
            else st.session_state["junctions_filtered"].to_dict("records"),
            lambda junction: junction["hms_element"],
            get_item_id=lambda junction: junction["hms_element"],
            feature_type=FeatureType.JUNCTION,
            image_path=os.path.join(assetsDir, "reaches_icon.png"),
        )
    with col_reservoirs:
        map_popover(
            "⬛ Reservoirs (HEC-HMS)",
            {}
            if st.session_state["reservoirs_filtered"] is None
            else st.session_state["reservoirs_filtered"].to_dict("records"),
            lambda reservoir: reservoir["hms_element"],
            get_item_id=lambda reservoir: reservoir["hms_element"],
            feature_type=FeatureType.RESERVOIR,
            image_path=os.path.join(assetsDir, "reaches_icon.png"),
        )
    with col_gages:
        map_popover(
            "🟢 Gages (USGS)",
            {}
            if st.session_state["gages_filtered"] is None
            else st.session_state["gages_filtered"].to_dict("records"),
            lambda gage: gage["site_no"],
            get_item_id=lambda gage: gage["site_no"],
            feature_type=FeatureType.GAGE,
            download_url=st.pilot_layers["Gages"],
            image_path=os.path.join(assetsDir, "gage_icon.png"),
        )
    with col_dams:
        map_popover(
            "🔴 Dams (NID)",
            {}
            if st.session_state["dams_filtered"] is None
            else st.session_state["dams_filtered"].to_dict("records"),
            lambda dam: dam["id"],
            get_item_id=lambda dam: dam["id"],
            feature_type=FeatureType.DAM,
            download_url=st.pilot_layers["Dams"],
            image_path=os.path.join(assetsDir, "dam_icon.jpg"),
        )
    with col_storms:
        map_popover(
            "🌧️ Storms",
            {},
            lambda storm: storm,
            get_item_id=lambda storm: storm,
            callback=lambda storm: st.session_state.update(
                {
                    "storm_layer": storm,
                    "single_event_focus_feature_type": FeatureType.STORM.value,
                    "single_event_focus_feature_id": storm,
                }
            ),
            feature_type=None,
            image_path=os.path.join(assetsDir, "storm_icon.png"),
        )

    # Create a map legend
    st.sidebar.markdown("## Map Legend")
    st.sidebar.markdown(
        f"""
        - 🟥 {num_bc_lines} BC Lines
        - 🟧 {num_ref_points} Reference Points
        - 🟫 {num_ref_lines} Reference Lines
        - 🟩 {num_models} Models
        - 🟦 {num_subbasins} Subbasins 
        - 🟪 {num_reaches} Reaches
        - 🟫 {num_junctions} Junctions
        - ⬛ {num_reservoirs} Reservoirs
        - 🟢 {num_gages} Gages 
        - 🔴 {num_dams} Dams 
        - 🌧️ 0 Storms
        """
    )

    # Session state
    with st.expander("Session State"):
        st.write(st.session_state)
        len_session_state = len(st.session_state)
        st.write(f"Session State Length: {len_session_state}")


if __name__ == "__main__":
    all_results()
