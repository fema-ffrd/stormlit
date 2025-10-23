# module imports
from utils.session import init_session_state
from utils.custom import stylable_container
from utils.metrics import calc_metrics, eval_metrics, define_metrics
from utils.nwis_api import query_nwis, select_usgs_gages
from utils.mapping import get_map_pos, prep_rasmap
from db.utils import create_pg_connection, create_s3_connection
from utils.plotting import (
    plot_ts,
    plot_hist,
)
from utils.stac_data import (
    reset_selections,
    init_ras_pilot,
    define_gage_data,
    define_dam_data,
    get_stac_img,
    get_stac_meta,
)
from utils.constants import FLOW_LABEL, WSE_LABEL, VELOCITY_LABEL
from db.pull import (
    query_s3_mod_flow,
    query_s3_mod_wse,
    query_s3_mod_vel,
    query_s3_mod_stage,
    query_s3_obs_flow,
    query_s3_calibration_event_list,
    query_s3_model_thumbnail,
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
            4. If selecting a model object, also select the event type and event ID:
            - **Single Event**: View deterministic results for a specific event.
                - Calibration events are historic simulations.
                - Stochastic events are synthetically generated.
            - **Multi Event**: View probabilistic results across an ensemble of stochastic events.
            5. After making a selection, statistics and analytics for that selection will be displayed to the right of the map.
            6. To reset selections, click the "Reset Selections" button located in the upper corner of the page
                """
            )


def ras_results():
    st.set_page_config(page_title="stormlit", page_icon=":rain_cloud:", layout="wide")
    if "session_id" not in st.session_state:
        init_session_state()

    st.title("RAS Model Results")

    # Sidebar configuration
    st.sidebar.markdown("# Page Navigation")
    st.sidebar.page_link("main.py", label="Home 🏠")
    st.sidebar.page_link("pages/model_qc.py", label="Model QC")
    st.sidebar.page_link("pages/hms_results.py", label="HMS Results")
    st.sidebar.page_link("pages/ras_results.py", label="RAS Results")
    # st.sidebar.page_link("pages/all_results.py", label="All Results")

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
    col_gages, col_dams, col_storms, reset_col = dropdown_container.columns(4)
    map_col, info_col = st.columns(2)

    with reset_col:
        if st.button("Reset Selections", type="primary", use_container_width=True):
            reset_selections()
            st.rerun()

    # Map Position
    c_lat, c_lon, zoom = get_map_pos("RAS")

    # Get the feature type from session state or default to None
    feature_type = st.session_state.get("single_event_focus_feature_type")
    if feature_type is not None:
        if feature_type not in FeatureType:
            # reset all session state related to feature focus
            reset_selections()
            st.rerun()
        else:
            feature_type = FeatureType(feature_type)

    # Map
    bbox = st.session_state.get("single_event_focus_bounding_box")
    with map_col:
        with st.spinner("Loading map..."):
            st.fmap = prep_rasmap(bbox, zoom, c_lat, c_lon)
            st.map_output = st.fmap.to_streamlit(height=500, bidirectional=True)

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
            elif feature_type == FeatureType.MODEL:
                feature_id = properties["model"]
                feature_label = feature_id
            elif feature_type == FeatureType.GAGE:
                feature_id = properties["site_no"]
                feature_label = feature_id
                st.session_state["model_id"] = identify_model(geom)
            elif feature_type == FeatureType.DAM:
                feature_id = properties["id"]
                feature_label = feature_id
                st.session_state["model_id"] = identify_model(geom)
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
                        ref_pt_vel_ts, on="time", how="outer", validate="one_to_one"
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
                            y_axis01_title=VELOCITY_LABEL,
                            y_axis02_title=WSE_LABEL,
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
                        bc_line_stage_ts, on="time", how="outer", validate="one_to_one"
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
                            y_axis01_title=WSE_LABEL,
                            y_axis02_title=FLOW_LABEL,
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
                        ref_line_wse_ts, on="time", how="outer", validate="one_to_one"
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
                                ref_line_flow_ts,
                                on="time",
                                how="outer",
                                validate="one_to_one",
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
                                y_axis01_title=FLOW_LABEL,
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
                                    value=float(gage_datum),
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
                                y_axis01_title=WSE_LABEL,
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
                                y_axis01_title=WSE_LABEL,
                                y_axis02_title=FLOW_LABEL,
                            )
                        with info_col.expander("Tables", expanded=False, icon="🔢"):
                            st.markdown("#### Reference Line Flow Data")
                            st.dataframe(ref_line_flow_ts)
                            st.markdown("#### Reference Line WSE Data")
                            st.dataframe(ref_line_wse_ts)
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
            num_bc_lines = len(st.session_state["bc_lines_filtered"])
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
            "🟥BC Lines",
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
            "🟧 Reference Points",
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
            "🟫 Reference Lines",
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
            "🟦 Models",
            st.models.to_dict("records"),
            lambda model: f"{model['model']}",
            get_item_id=lambda model: model["model"],
            feature_type=FeatureType.MODEL,
            image_path=os.path.join(assetsDir, "model_icon.jpg"),
        )
    with col_gages:
        map_popover(
            "🟩 Gages",
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
            "🟥 Dams",
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
    if st.session_state["model_id"] is not None:
        st.sidebar.markdown(f"#### Filtered to `{st.session_state['model_id']}`")
    st.sidebar.markdown(
        f"""
        - 🟥 {num_bc_lines} BC Lines
        - 🟧 {num_ref_points} Reference Points
        - 🟫 {num_ref_lines} Reference Lines
        - 🟦 {num_models} Models
        - 🟩 {num_gages} Gages
        - 🟥 {num_dams} Dams
        - 🌧️ 0 Storms
        """
    )

    if os.getenv("SHOW_SESSION_STATE") == "True":
        with st.expander("Session State", expanded=False):
            st.json(st.session_state)


if __name__ == "__main__":
    ras_results()
