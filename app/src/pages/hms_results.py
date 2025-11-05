# module imports
from utils.session import init_session_state
from utils.nwis_api import query_nwis
from db.utils import create_pg_connection, create_s3_connection
from utils.custom import about_popover, map_popover
from utils.mapping import (
    prep_hmsmap,
    get_map_pos,
    get_gis_legend_stats,
    get_hms_legend_stats,
    get_model_subbasin,
    get_gage_from_subbasin,
    get_gage_from_pt_ln,
)
from utils.plotting import (
    plot_ts,
    plot_flow_aep,
    plot_multi_event_ts,
)
from utils.stac_data import (
    reset_selections,
    init_hms_pilot,
    define_gage_data,
    define_dam_data,
    get_stac_img,
    get_stac_meta,
)
from utils.constants import (
    FLOW_LABEL,
    CALIB_EVENTS,
    STOCHASTIC_EVENTS,
    MULTI_EVENTS,
)
from db.pull import (
    query_s3_obs_flow,
    query_s3_stochastic_hms_flow,
    query_s3_folder_names,
    query_s3_ams_peaks_by_element,
    query_s3_gage_ams,
)

# standard imports
import os
import logging
from enum import Enum

# third party imports
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from urllib.parse import urljoin
from shapely.geometry import shape

currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
assetsDir = os.path.abspath(os.path.join(srcDir, "assets"))  # go up one level to src
load_dotenv()

logger = logging.getLogger(__name__)


class FeatureType(Enum):
    GAGE = "Gage"
    DAM = "Dam"
    SUBBASIN = "Subbasin"
    REACH = "Reach"
    JUNCTION = "Junction"
    RESERVOIR = "Reservoir"
    COG = "Raster Layer"
    STORM = "Storm"


def calibration_events():
    st.write("Coming soon...")
    st.session_state["stochastic_event"] = None
    st.session_state["stochastic_storm"] = None


def stochastic_events(
    col_storm_id, col_event_id, info_col, feature_type, feature_label
):
    """Handle stochastic events selection and display."""
    if st.session_state["hms_element_id"] is None:
        st.warning(
            "Please select a HEC-HMS model object from the map or drop down list"
        )
    else:
        stochastic_storms = query_s3_folder_names(
            st.session_state["s3_conn"],
            s3_path=f"s3://{st.session_state['pilot']}/cloud-hms-db/simulations/element={st.session_state['hms_element_id']}/",
            folder_name="storm_id=",
        )
        st.session_state["stochastic_storm"] = col_storm_id.selectbox(
            "Select Storm ID",
            sorted(stochastic_storms),
            index=None,
        )
        if st.session_state["stochastic_storm"] is None:
            st.warning("Please select a stochastic storm.")
        else:
            stochastic_events = query_s3_folder_names(
                st.session_state["s3_conn"],
                s3_path=f"s3://{st.session_state['pilot']}/cloud-hms-db/simulations/element={st.session_state['hms_element_id']}/storm_id={st.session_state['stochastic_storm']}/",
                folder_name="event_id=",
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
            flow_type="FLOW",
        )
        stochastic_flow_ts.rename(columns={"hms_flow": "Hydrograph"}, inplace=True)
        if feature_type == FeatureType.SUBBASIN:
            stochastic_baseflow_ts = query_s3_stochastic_hms_flow(
                st.session_state["s3_conn"],
                st.session_state["pilot"],
                st.session_state["hms_element_id"],
                st.session_state["stochastic_storm"],
                st.session_state["stochastic_event"],
                flow_type="FLOW-BASE",
            )
            stochastic_baseflow_ts.rename(
                columns={"hms_flow": "Baseflow"}, inplace=True
            )
        else:
            stochastic_baseflow_ts = pd.DataFrame()
            st.markdown("Baseflow is not available for this HMS element. ")
        info_col.markdown("### Modeled Flow")
        with info_col.expander("Plots", expanded=False, icon="📈"):
            plot_ts(
                stochastic_flow_ts,
                stochastic_baseflow_ts,
                "Hydrograph",
                "Baseflow",
                dual_y_axis=False,
                plot_title=feature_label,
                y_axis01_title=FLOW_LABEL,
            )
        with info_col.expander("Tables", expanded=False, icon="🔢"):
            st.markdown("#### Modeled Hydrograph")
            st.dataframe(stochastic_flow_ts)
            st.markdown("#### Modeled Baseflow")
            st.dataframe(stochastic_baseflow_ts)


def multi_events(available_gage_ids, col_storm_id, info_col, feature_type):
    """Handle multi events selection and display."""
    if st.session_state["hms_element_id"] is None:
        st.warning(
            "Please select a HEC-HMS model object from the map or drop down list"
        )
    else:
        if available_gage_ids is not None:
            st.session_state["multi_event_gage_id"] = col_storm_id.selectbox(
                "Select Gage ID",
                available_gage_ids,
                index=0,
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
                            gage_flow_ts["storm_id"] = selected_points[point][
                                "storm_id"
                            ]
                            gage_flow_ts["event_id"] = selected_points[point][
                                "event_id"
                            ]
                            multi_events_flows.append(gage_flow_ts)
                        else:
                            peak_time = selected_points[point]["peak_time"]
                            peak_time_dt = pd.to_datetime(
                                peak_time,
                                format="%Y-%m-%d",
                                errors="coerce",
                            )
                            start_date = (peak_time_dt - pd.Timedelta(days=1)).strftime(
                                "%Y-%m-%d"
                            )
                            end_date = (peak_time_dt + pd.Timedelta(days=1)).strftime(
                                "%Y-%m-%d"
                            )
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
                                gage_flow_ts["storm_id"] = selected_points[point][
                                    "storm_id"
                                ]
                                gage_flow_ts["event_id"] = selected_points[point][
                                    "event_id"
                                ]
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
                        stochastic_flow_ts["storm_id"] = selected_points[point][
                            "storm_id"
                        ]
                        stochastic_flow_ts["event_id"] = selected_points[point][
                            "event_id"
                        ]
                        multi_events_flows.append(stochastic_flow_ts)
                        if feature_type == FeatureType.SUBBASIN:
                            # Get the Stochastic Baseflows
                            stochastic_baseflow_ts = query_s3_stochastic_hms_flow(
                                st.session_state["s3_conn"],
                                st.session_state["pilot"],
                                st.session_state["hms_element_id"],
                                selected_points[point]["storm_id"],
                                selected_points[point]["event_id"],
                                flow_type="FLOW-BASE",
                            )
                            stochastic_baseflow_ts["block_id"] = point
                            stochastic_baseflow_ts["storm_id"] = selected_points[point][
                                "storm_id"
                            ]
                            stochastic_baseflow_ts["event_id"] = selected_points[point][
                                "event_id"
                            ]
                            multi_events_baseflows.append(stochastic_baseflow_ts)
                        else:
                            st.warning(
                                "Baseflow is not available for this HMS element."
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
                    plot_multi_event_ts(multi_events_flows_df, pd.DataFrame())
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


def hms_results():
    st.set_page_config(page_title="stormlit", page_icon=":rain_cloud:", layout="wide")
    if "session_id" not in st.session_state:
        init_session_state()

    # Initialize map version if not already set
    if "map_version" not in st.session_state:
        st.session_state["map_version"] = 0

    st.title("HMS Model Results")

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
    if st.session_state["init_hms_pilot"] is False:
        with st.spinner("Initializing HMS datasets..."):
            init_hms_pilot(
                st.session_state["s3_conn"],
                st.session_state["pilot"],
            )
            st.session_state["init_hms_pilot"] = True
    dropdown_container = st.container(
        key="dropdown_container",
    )
    # Dropdowns for selecting features
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
    c_lat, c_lon, zoom = get_map_pos("HMS")

    # Get the feature type from session state or default to None to determine how to display the map
    feature_type = st.session_state.get("single_event_focus_feature_type")
    if feature_type is not None:
        if feature_type not in FeatureType:
            reset_selections()
            st.rerun()
        else:
            feature_type = FeatureType(feature_type)

    bbox = st.session_state.get("single_event_focus_bounding_box")
    with map_col:
        with st.spinner("Loading map..."):
            # Use map_version as key to force re-render on reset
            st.fmap = prep_hmsmap(bbox, zoom, c_lat, c_lon)
            st.map_output = st.fmap.to_streamlit(
                height=500,
                bidirectional=True,
            )

    # Handle when a feature is selected from the map
    last_active_drawing = st.map_output.get("last_active_drawing", None)

    if last_active_drawing:
        logger.debug("Map feature selected")
        properties = last_active_drawing.get("properties", {})
        layer = properties.get("layer")
        geom = last_active_drawing.get("geometry", None)
        st.session_state["current_map_feature"] = last_active_drawing
        if geom and isinstance(geom, dict):
            geom = shape(geom)
        if layer:
            feature_type = FeatureType(layer)
            if feature_type == FeatureType.SUBBASIN:
                feature_id = properties["hms_element"]
                feature_label = feature_id
                st.session_state["subbasin_id"] = feature_id
            elif feature_type in (
                FeatureType.REACH,
                FeatureType.JUNCTION,
                FeatureType.RESERVOIR,
            ):
                feature_id = properties["hms_element"]
                feature_label = feature_id
                st.session_state["subbasin_id"] = get_model_subbasin(
                    geom, st.subbasins, "hms_element"
                )
                st.session_state["hms_element_id"] = feature_label
            elif feature_type == FeatureType.GAGE:
                feature_id = properties["site_no"]
                feature_label = feature_id
                st.session_state["subbasin_id"] = get_model_subbasin(
                    geom, st.subbasins, "hms_element"
                )
                st.session_state["hms_element_id"] = None
            elif feature_type == FeatureType.DAM:
                feature_id = properties["id"]
                feature_label = feature_id
                st.session_state["subbasin_id"] = get_model_subbasin(
                    geom, st.subbasins, "hms_element"
                )
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
        # NID Dams
        if feature_type == FeatureType.DAM:
            info_col.markdown(f"### Subbasin: `{st.session_state['subbasin_id']}`")
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
            info_col.markdown(f"### Subbasin: `{st.session_state['subbasin_id']}`")
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
        # HEC-HMS Model Objects
        elif feature_type in [
            FeatureType.SUBBASIN,
            FeatureType.REACH,
            FeatureType.JUNCTION,
            FeatureType.RESERVOIR,
        ]:
            st.session_state["hms_element_id"] = feature_label
            st.markdown(f"### Subbasin: `{st.session_state['subbasin_id']}`")
            if feature_type != FeatureType.SUBBASIN:
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
                [CALIB_EVENTS, STOCHASTIC_EVENTS, MULTI_EVENTS],
                index=0,
            )
            if feature_type == FeatureType.SUBBASIN:
                available_gage_ids = get_gage_from_subbasin(
                    st.subbasins.loc[st.subbasins["hms_element"] == feature_label][
                        "geometry"
                    ]
                )
            elif feature_type == FeatureType.REACH:
                available_gage_ids = get_gage_from_pt_ln(
                    st.reaches.loc[st.reaches["hms_element"] == feature_label][
                        "geometry"
                    ]
                )
            elif feature_type == FeatureType.JUNCTION:
                available_gage_ids = get_gage_from_pt_ln(
                    st.junctions.loc[st.junctions["hms_element"] == feature_label][
                        "geometry"
                    ]
                )
            elif feature_type == FeatureType.RESERVOIR:
                available_gage_ids = get_gage_from_pt_ln(
                    st.reservoirs.loc[st.reservoirs["hms_element"] == feature_label][
                        "geometry"
                    ]
                )
            else:
                available_gage_ids = None

            if st.session_state["event_type"] == STOCHASTIC_EVENTS:
                stochastic_events(
                    col_storm_id, col_event_id, info_col, feature_type, feature_label
                )
            elif st.session_state["event_type"] == MULTI_EVENTS:
                multi_events(available_gage_ids, col_storm_id, info_col, feature_type)
            elif st.session_state["event_type"] == CALIB_EVENTS:
                calibration_events()
            else:
                pass
        else:
            st.markdown(
                """
                ### Begin by selecting a feature from the map or dropdown.
            1. **Map**: select any feature to generate selections based on that feature's geometry.
            2.  **Dropdown**: select a HEC-HMS subbasin to generate additional selections within the other 
            dropdowns that are then filtered to be within that subbasin.
                """
            )

    with dropdown_container:
        if st.session_state["subbasin_id"] is not None:
            selected_subbasin = st.subbasins[
                st.subbasins["hms_element"] == st.session_state["subbasin_id"]
            ]
            num_subbasins = get_hms_legend_stats(
                selected_subbasin, st.subbasins, "subbasins_filtered"
            )
            num_reaches = get_hms_legend_stats(
                selected_subbasin, st.reaches, "reaches_filtered"
            )
            num_junctions = get_hms_legend_stats(
                selected_subbasin, st.junctions, "junctions_filtered"
            )
            num_reservoirs = get_hms_legend_stats(
                selected_subbasin, st.reservoirs, "reservoirs_filtered"
            )
            num_gages = get_gis_legend_stats(
                st.gages,
                "gages_filtered",
                st.subbasins,
                "hms_element",
                st.session_state["subbasin_id"],
            )
            num_dams = get_gis_legend_stats(
                st.dams,
                "dams_filtered",
                st.subbasins,
                "hms_element",
                st.session_state["subbasin_id"],
            )

    # Dropdowns for each feature type
    with col_subbasins:
        map_popover(
            "🟦 Subbasins",
            st.subbasins.to_dict("records"),
            lambda subbasin: subbasin["hms_element"],
            get_item_id=lambda subbasin: subbasin["hms_element"],
            feature_type=FeatureType.SUBBASIN,
            image_path=os.path.join(assetsDir, "subbasins_icon.png"),
        )
    with col_reaches:
        map_popover(
            "🟪 Reaches",
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
            "🟫 Junctions",
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
            "⬛ Reservoirs",
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

    with st.sidebar:
        pilot_stats, selection_stats = st.tabs(["Pilot", "Selection"])
        pilot_stats.markdown(
            f"""
            - 🟦 {len(st.subbasins)} Subbasins 
            - 🟪 {len(st.reaches)} Reaches
            - 🟫 {len(st.junctions)} Junctions
            - ⬛ {len(st.reservoirs)} Reservoirs
            - 🟩 {len(st.gages)} Gages 
            - 🟥 {len(st.dams)} Dams 
            - 🌧️ 0 Storms
            """
        )
        if st.session_state["subbasin_id"] is not None:
            selection_stats.markdown(
                f"""
                #### Filtered to `{st.session_state["subbasin_id"]}`
                - 🟦 {num_subbasins} Subbasins 
                - 🟪 {num_reaches} Reaches
                - 🟫 {num_junctions} Junctions
                - ⬛ {num_reservoirs} Reservoirs
                - 🟩 {num_gages} Gages 
                - 🟥 {num_dams} Dams 
                - 🌧️ 0 Storms
                """
            )

    if os.getenv("SHOW_SESSION_STATE") is True:
        with st.expander("Session State", expanded=False):
            st.json(st.session_state)


if __name__ == "__main__":
    hms_results()
