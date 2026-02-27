# module imports
from utils.session import init_session_state
from db.query_meta_tables import query_iceberg_table
from utils.storms import (
    compute_storm,
    compute_hyetograph,
    compute_storm_animation,
    build_storm_animation_maplibre,
)
from utils.custom import about_popover_met
from utils.mapping import prep_metmap, get_map_pos
from utils.stac_data import init_met_pilot, get_stac_meta
from utils.projects import load_projects

# standard imports
import os
import time
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


def _update_selected_storm(storms_df, row_idx, id_column, aorc_storm_href):
    if storms_df is None or row_idx is None or row_idx >= len(storms_df):
        return
    storm_id = int(storms_df.iloc[row_idx][id_column])
    st.session_state.update(
        {
            "hydromet_storm_id": storm_id,
            "single_event_focus_feature_type": FeatureType.STORM.value,
            "single_event_focus_feature_id": storm_id,
            "aorc_storm_href": aorc_storm_href,
        }
    )


def _handle_storm_select(event=None):
    row_idx = _get_selected_row(event, "storms_table_rank")
    storms_df = st.session_state.get("storms_df_rank")
    aorc_storm_href = None
    if storms_df is not None and row_idx is not None and row_idx < len(storms_df):
        aorc_storm_href = storms_df.iloc[row_idx].get("aorc_storm_href")
    _update_selected_storm(storms_df, row_idx, "rank", aorc_storm_href)


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
    st.sidebar.markdown("## Getting Started")
    with st.sidebar:
        about_popover_met()

    st.sidebar.markdown("## Select Study")
    config_path = os.path.join(srcDir, "configs", "projects.yaml")
    if not os.path.exists(config_path):
        st.error(f"Project configuration file not found: {config_path}")
        return
    projects = load_projects(config_path)
    project_names = [project.name for project in projects]
    st.session_state["pilot"] = st.sidebar.selectbox(
        "Select a Pilot Study",
        project_names,
        index=None,
    )

    if st.session_state["pilot"] is None:
        st.warning("Please select a pilot study from the sidebar to begin.")
        return

    pilot_name = st.session_state["pilot"]
    # get the pilot target bucket
    active_pilot = st.session_state.get("active_met_pilot")
    if active_pilot != pilot_name:
        st.session_state["hydromet_storm_id"] = None
        st.session_state["aorc_storm_href"] = None
        st.session_state["storms_df_rank"] = None
        st.session_state["hyeto_cache"] = {}
        st.session_state["storm_cache"] = None
        st.session_state["storm_bounds"] = None
        st.session_state["clipped_storm_bounds"] = None
        st.session_state["storm_animation_payload"] = None
        st.session_state["storm_animation_requested"] = False
        st.session_state["storm_animation_html"] = None
        st.session_state["storm_animation_storm_id"] = None
        st.session_state["aorc:transform"] = None

    if (
        active_pilot != pilot_name
        or not st.pilot_layers
        or "Storms" not in st.pilot_layers
    ):
        with st.spinner("Initializing Meteorology datasets..."):
            init_met_pilot(pilot_name, config_path)

    st.session_state.setdefault("hyeto_cache", {})

    map_col, info_col = st.columns(2)
    map_tab, session_tab = map_col.tabs(["Map", "Session State"])
    selections_tab, metadata_tab, hyeto_tab, anime_tab = info_col.tabs(
        ["Selections", "Metadata", "Hyetographs", "Animation"]
    )
    # Selection Panel
    with selections_tab:
        st.markdown("## Storm Selection")
        st.info(
            "Query storms from the catalog. Afterwards sort by rank, storm type, or date using the table headers."
        )

        st.session_state["num_storms"] = st.number_input(
            "Select number of rows to return",
            min_value=1,
            max_value=450,
            value=10,
            step=10,
        )
        if st.session_state["num_storms"] is not None:
            st.session_state["storms_df_rank"] = query_iceberg_table(
                table_name="storms",
                target_bucket=st.session_state["pilot_bucket"],
                num_rows=st.session_state["num_storms"],
            )
            st.info(
                "Select a single storm from the table below to view its metadata, map location, hyetographs, and animation."
            )
            if st.session_state["storms_df_rank"] is not None:
                st.dataframe(
                    st.session_state["storms_df_rank"],
                    width="stretch",
                    selection_mode="single-row",
                    on_select=_handle_storm_select,
                    key="storms_table_rank",
                )
            else:
                st.warning("No storms found for this study.")

    # Compute storm data if a storm is selected
    if st.session_state["hydromet_storm_id"] is not None:
        compute_storm(
            storm_id=st.session_state["hydromet_storm_id"],
            aorc_storm_href=st.session_state["aorc_storm_href"],
            tab=info_col,
        )
    # Metadata Panel
    with metadata_tab:
        st.markdown("## Storm Metadata")
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
        st.markdown("## Storm Cache")
        st.write(st.session_state.get("hydromet_storm_data", None))
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
            aorc_storm_href = st.session_state["aorc_storm_href"]
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
                    storm_id=storm_id,
                    aorc_storm_href=aorc_storm_href,
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
                        storm_id=st.session_state["hydromet_storm_id"],
                        aorc_storm_href=st.session_state["aorc_storm_href"],
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
                            start_time = time.time()
                            st.session_state["storm_animation_html"] = (
                                build_storm_animation_maplibre(
                                    animation_payload.get("frames"),
                                    animation_payload.get("times"),
                                    st.session_state.get("storm_bounds"),
                                )
                            )
                            end_time = time.time()
                            elapsed_time = (end_time - start_time) / 60
                            st.write(
                                f"Animation rendering took {elapsed_time:.2f} minutes."
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
