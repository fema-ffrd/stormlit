# module imports
from utils.session import init_session_state
from db.pull import (
    query_storms_by_threshold,
    query_storms_by_rank,
    query_storms_by_date,
)
from db.utils import create_pg_connection, create_s3_connection
from db.icechunk import (
    open_repo,
    open_session,
)
from utils.storms import (
    compute_storm,
    compute_hyetograph,
    compute_storm_animation,
    build_storm_animation_maplibre,
)
from utils.custom import about_popover_met
from utils.mapping import prep_metmap, get_map_pos
from utils.stac_data import init_met_pilot, get_stac_meta

# standard imports
import os
import logging
from enum import Enum

# third party imports
import yaml
import streamlit as st
from dotenv import load_dotenv
import plotly.graph_objects as go
from streamlit.components.v1 import html as components_html

currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
assetsDir = os.path.abspath(os.path.join(srcDir, "assets"))  # go up one level to src
load_dotenv()

logger = logging.getLogger(__name__)


class FeatureType(Enum):
    MODEL = "Model"
    STORM = "Storm"


def _get_selected_row(event, table_key):
    if event is not None:
        selection = getattr(event, "selection", None)
        rows = getattr(selection, "rows", []) if selection is not None else []
    else:
        table_state = st.session_state.get(table_key, {})
        selection = table_state.get("selection", {})
        rows = selection.get("rows", [])
    return rows[0] if rows else None


def _update_selected_storm(storms_df, row_idx, id_column):
    if storms_df is None or row_idx is None or row_idx >= len(storms_df):
        return
    storm_id = int(storms_df.iloc[row_idx][id_column])
    st.session_state.update(
        {
            "hydromet_storm_id": storm_id,
            "single_event_focus_feature_type": FeatureType.STORM.value,
            "single_event_focus_feature_id": storm_id,
        }
    )


def _handle_rank_select(event=None):
    row_idx = _get_selected_row(event, "storms_table_rank")
    storms_df = st.session_state.get("storms_df_rank")
    _update_selected_storm(storms_df, row_idx, "rank")


def _handle_precip_select(event=None):
    row_idx = _get_selected_row(event, "storms_table_precip")
    storms_df = st.session_state.get("storms_df_precip")
    _update_selected_storm(storms_df, row_idx, "rank")


def _handle_date_select(event=None):
    row_idx = _get_selected_row(event, "storms_table_date")
    storms_df = st.session_state.get("storms_df_date")
    _update_selected_storm(storms_df, row_idx, "rank")


def met():
    st.set_page_config(page_title="stormlit", page_icon=":rain_cloud:", layout="wide")
    if "session_id" not in st.session_state:
        init_session_state()
    st.title("Meteorology")
    # Sidebar configuration
    st.sidebar.markdown("# Page Navigation")
    st.sidebar.page_link("main.py", label="Home 🏠")
    st.sidebar.page_link("pages/model_qc.py", label="Model QC")
    st.sidebar.page_link("pages/hms_results.py", label="HMS Results")
    st.sidebar.page_link("pages/ras_results.py", label="RAS Results")
    st.sidebar.page_link("pages/met_results.py", label="Meteorology")
    # st.sidebar.page_link("pages/all_results.py", label="All Results")
    st.sidebar.markdown("## Getting Started")
    with st.sidebar:
        about_popover_met()
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
    if st.session_state["init_met_pilot"] is False:
        with st.spinner("Initializing Meteorology datasets..."):
            init_met_pilot(
                st.session_state["s3_conn"],
                st.session_state["pilot"],
            )
            st.session_state["init_met_pilot"] = True
    st.session_state.setdefault("storm_cache", {})
    st.session_state.setdefault("hyeto_cache", {})
    repo = open_repo(
        bucket=st.session_state["pilot"], prefix="test/trinity-storms.icechunk"
    )
    ds = open_session(repo=repo, branch="main")
    map_col, info_col = st.columns(2)
    map_tab, session_tab = map_col.tabs(["Map", "Session State"])
    selections_tab, metadata_tab, hyeto_tab, anime_tab = info_col.tabs(
        ["Selections", "Metadata", "Hyetographs", "Animation"]
    )
    # Selection Panel
    with selections_tab:
        st.markdown("## Storm Selection")
        rank_tab, precip_tab, date_tab = st.tabs(
            ["By Rank", "By Precipitation", "By Date"]
        )
        with rank_tab:
            st.info("Query the top N ranked storms from the catalog.")

            st.session_state["rank_threshold"] = st.number_input(
                "Select a Minimum Rank Threshold (1 = highest rank = largest storm)",
                min_value=1,
                max_value=440,
                value=10,
                step=10,
            )
            if st.session_state["rank_threshold"] is not None:
                st.session_state["storms_df_rank"] = query_storms_by_rank(
                    st.session_state["s3_conn"],
                    st.session_state["pilot"],
                    st.pilot_layers["Storms"],
                    rank=st.session_state["rank_threshold"],
                )
                st.info(
                    "Click on a row to select a storm and view its details, map location, and hyetograph."
                )
                st.dataframe(
                    st.session_state["storms_df_rank"],
                    width="stretch",
                    selection_mode="single-row",
                    on_select=_handle_rank_select,
                    key="storms_table_rank",
                )
        with precip_tab:
            st.info(
                "Query storms from the catalog that exceed a specified precipitation threshold."
            )
            st.session_state["precip_threshold"] = st.number_input(
                "Select a Minimum Precipitation Threshold (inches)",
                min_value=0.0,
                max_value=20.0,
                value=7.0,
                step=0.5,
            )
            if st.session_state["precip_threshold"] is not None:
                st.session_state["storms_df_precip"] = query_storms_by_threshold(
                    st.session_state["s3_conn"],
                    st.session_state["pilot"],
                    st.pilot_layers["Storms"],
                    threshold=st.session_state["precip_threshold"],
                )
                st.info(
                    "Click on a row to select a storm and view its details, map location, and hyetograph."
                )
                st.dataframe(
                    st.session_state["storms_df_precip"],
                    width="stretch",
                    selection_mode="single-row",
                    on_select=_handle_precip_select,
                    key="storms_table_precip",
                )
        with date_tab:
            st.info(
                "Query storms from the catalog that occurred within a specified date range."
            )
            start_date_col, end_date_col = st.columns(2)
            st.session_state["storm_start_date"] = start_date_col.date_input(
                "Start Date"
            )
            st.session_state["storm_end_date"] = end_date_col.date_input("End Date")
            if (
                st.session_state["storm_start_date"]
                and st.session_state["storm_end_date"]
                and st.session_state["storm_start_date"]
                <= st.session_state["storm_end_date"]
            ):
                st.session_state["storms_df_date"] = query_storms_by_date(
                    st.session_state["s3_conn"],
                    st.session_state["pilot"],
                    st.pilot_layers["Storms"],
                    start_date=st.session_state["storm_start_date"],
                    end_date=st.session_state["storm_end_date"],
                )
                st.info(
                    "Click on a row to select a storm and view its details, map location, and hyetograph."
                )
                st.dataframe(
                    st.session_state["storms_df_date"],
                    width="stretch",
                    selection_mode="single-row",
                    on_select=_handle_date_select,
                    key="storms_table_date",
                )
    # Compute storm data if a storm is selected
    if st.session_state["hydromet_storm_id"] is not None:
        compute_storm(ds, storm_id=st.session_state["hydromet_storm_id"], tab=info_col)
    # Metadata Panel
    with metadata_tab:
        st.markdown("## Storm Metadata")
        if ds is None:
            st.sidebar.error("Failed to load Meteorology data. Dataset is None.")
            st.info("Unable to display metadata until the dataset loads.")
        else:
            st.sidebar.success("Meteorology data loaded successfully.")
            storm_id = st.session_state["hydromet_storm_id"]
            if storm_id is None:
                st.info("Please select a storm.")
            else:
                storm_meta = get_stac_meta(
                    st.pilot_layers["Metadata"] + f"{storm_id}" + f"/{storm_id}.json"
                )
                if storm_meta[0]:
                    storm_meta = storm_meta[1]
                    storm_prop = storm_meta.get("properties", {})
                    st.session_state["aorc:transform"] = storm_prop.get(
                        "aorc:transform", None
                    )
                    storm_prop_yaml = yaml.dump(storm_prop, sort_keys=False)
                    st.text(storm_prop_yaml)
                else:
                    st.error(
                        f"Failed to retrieve metadata for Storm ID {storm_id}: {storm_meta[1]}"
                    )
    # Map Panel
    with map_tab:
        if st.session_state["hydromet_storm_id"] is not None:
            st.markdown(
                f"## Selected Storm ID: {st.session_state['hydromet_storm_id']}"
            )
            st.markdown("### 72-hour Accumulated Precipitation")
        c_lat, c_lon, zoom = get_map_pos("MET")
        with st.spinner("Loading map..."):
            st.fmap = prep_metmap(
                zoom,
                c_lat,
                c_lon,
                storm_id=st.session_state["hydromet_storm_id"],
            )
            st.map_output = st.fmap.to_streamlit(height=500, bidirectional=True)
    # Session State Panel
    with session_tab:
        st.markdown("## Map State")
        last_active_drawing = st.map_output.get("last_active_drawing", None)
        st.write(st.map_output["all_drawings"])
        if last_active_drawing:
            logger.debug("Map feature selected")
            geometry = last_active_drawing.get("geometry", {})
            if geometry["type"] == "Point":
                coordinates = geometry.get("coordinates", None)
                if coordinates:
                    map_lon, map_lat = coordinates
                    st.session_state.update(
                        {
                            "single_event_focus_lat": map_lat,
                            "single_event_focus_lon": map_lon,
                            "single_event_focus_map_click": True,
                        }
                    )
    # Hyetograph Panel
    with hyeto_tab:
        st.markdown("## Storm Hyetographs")
        if st.session_state["hydromet_storm_id"] is None:
            st.info("Please select a storm.")
        elif st.map_output.get("all_drawings") is None:
            st.info(
                "Drop one or multiple points as markers on the map to view hyetographs."
            )
        else:
            storm_id = st.session_state["hydromet_storm_id"]
            hyeto_cache = st.session_state.setdefault("hyeto_cache", {})
            added_points = False
            for drawing in st.map_output["all_drawings"]:
                geometry = drawing.get("geometry", {})
                if geometry.get("type") != "Point":
                    continue
                coordinates = geometry.get("coordinates", [])
                if len(coordinates) != 2:
                    continue
                lon, lat = coordinates
                cache_key = (lat, lon, storm_id)
                if cache_key in hyeto_cache:
                    continue
                compute_hyetograph(
                    ds,
                    storm_id=storm_id,
                    lat=lat,
                    lon=lon,
                    tab=hyeto_tab,
                )
                added_points = True
            if added_points:
                st.rerun()
        with st.expander("Plots", expanded=True, icon="📈"):
            if st.session_state.get("hyeto_cache"):
                fig = go.Figure()
                for key, hyeto_da in st.session_state["hyeto_cache"].items():
                    lat, lon, storm_id = key
                    if storm_id != st.session_state["hydromet_storm_id"]:
                        continue
                    hyeto_df = hyeto_da.to_dataframe(name="precip_in").reset_index()
                    time_cols = [
                        col for col in ("abs_time", "time") if col in hyeto_df.columns
                    ]
                    if time_cols:
                        x_col = time_cols[0]
                    else:
                        hyeto_df["timestep"] = range(len(hyeto_df))
                        x_col = "timestep"

                    fig.add_trace(
                        go.Scatter(
                            x=hyeto_df[x_col],
                            y=hyeto_df["precip_in"],
                            mode="lines+markers",
                            name=f"Lat {lat:.4f}, Lon {lon:.4f}",
                        )
                    )

                fig.update_layout(
                    title="Hyetographs",
                    xaxis_title="Time",
                    yaxis_title="Precipitation (inches)",
                    margin=dict(l=20, r=20, t=40, b=20),
                    legend_title_text="Locations",
                )
                st.plotly_chart(fig, width="stretch")
        with st.expander("Tables", expanded=False, icon="🔢"):
            if st.session_state.get("hyeto_cache"):
                for key, hyeto_da in st.session_state["hyeto_cache"].items():
                    lat, lon, storm_id = key
                    if storm_id != st.session_state["hydromet_storm_id"]:
                        continue
                    hyeto_df = hyeto_da.to_dataframe(name="precip_in").reset_index()
                    hyeto_df_display = hyeto_df.copy()
                    time_cols = [
                        col for col in ("abs_time", "time") if col in hyeto_df.columns
                    ]
                    if time_cols:
                        x_col = time_cols[0]
                        hyeto_df_display[x_col] = hyeto_df_display[x_col].astype(str)
                    else:
                        hyeto_df_display["timestep"] = range(len(hyeto_df_display))

                    st.markdown(f"### Lat {lat:.4f}, Lon {lon:.4f}")
                    st.dataframe(hyeto_df_display, width="stretch")
    # Animation Panel
    with anime_tab:
        st.markdown("## Storm Animation")
        st.session_state.setdefault("storm_animation_requested", False)
        st.session_state.setdefault("storm_animation_html", None)
        if ds is None:
            st.info("Dataset not loaded yet.")
        else:
            if st.session_state["hydromet_storm_id"] is None:
                st.info("Please select a storm.")
            else:
                if st.button(
                    "Generate Animation",
                    type="primary",
                    use_container_width=True,
                ):
                    st.session_state["storm_animation_requested"] = True
                    st.session_state["storm_animation_html"] = None
                    with st.spinner("Computing animation frames..."):
                        compute_storm_animation(
                            ds, storm_id=st.session_state["hydromet_storm_id"]
                        )

                animation_payload = st.session_state.get("storm_animation_payload")
                if st.session_state.get("storm_animation_html"):
                    components_html(
                        st.session_state["storm_animation_html"],
                        height=500,
                        scrolling=False,
                    )
                elif not st.session_state.get("storm_animation_requested"):
                    st.info(
                        "Click the button above to generate an animation for the selected storm."
                    )
                elif animation_payload and animation_payload.get("frames") is not None:
                    if st.session_state.get("storm_bounds") is None:
                        st.warning(
                            "Storm bounds not available yet. Try again after the map loads."
                        )
                    else:
                        if st.session_state.get("storm_animation_html") is None:
                            with st.spinner("Rendering animation..."):
                                st.session_state["storm_animation_html"] = (
                                    build_storm_animation_maplibre(
                                        animation_payload.get("frames"),
                                        animation_payload.get("times"),
                                        st.session_state.get("storm_bounds"),
                                    )
                                )
                        if st.session_state["storm_animation_html"]:
                            components_html(
                                st.session_state["storm_animation_html"],
                                height=650,
                                scrolling=False,
                            )
                        else:
                            st.warning("Unable to render animation for this storm.")
                else:
                    st.warning("Animation frames are not ready. Try again.")


if __name__ == "__main__":
    met()
