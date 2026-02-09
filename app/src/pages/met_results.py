# module imports
from utils.session import init_session_state
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
from utils.custom import about_popover, map_popover
from utils.mapping import prep_metmap, get_map_pos
from utils.stac_data import init_met_pilot, get_stac_meta

# standard imports
import os
import logging
from enum import Enum

# third party imports
import streamlit as st
from dotenv import load_dotenv
import plotly.express as px
from streamlit.components.v1 import html as components_html

currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
assetsDir = os.path.abspath(os.path.join(srcDir, "assets"))  # go up one level to src
load_dotenv()

logger = logging.getLogger(__name__)


class FeatureType(Enum):
    MODEL = "Model"
    STORM = "Storm"


def hydro_met():
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
    if st.session_state["init_met_pilot"] is False:
        with st.spinner("Initializing Meteorology datasets..."):
            init_met_pilot(
                st.session_state["s3_conn"],
                st.session_state["pilot"],
            )
            st.session_state["init_met_pilot"] = True
    st.session_state.setdefault("storm_cache", {})

    repo = open_repo(
        bucket=st.session_state["pilot"], prefix="test/trinity-storms.icechunk"
    )
    ds = open_session(repo=repo, branch="main")

    map_col, info_col = st.columns(2)

    with map_col:
        map_popover(
            "🌧️ Storms",
            range(1, 441),
            lambda storm: storm,
            get_item_id=lambda storm: storm,
            callback=lambda storm: st.session_state.update(
                {
                    "hydromet_storm_id": storm,
                    "single_event_focus_feature_type": FeatureType.STORM.value,
                    "single_event_focus_feature_id": storm,
                }
            ),
            feature_type=None,
            image_path=os.path.join(assetsDir, "storm_icon.png"),
        )

    metadata_tab, hyeto_tab, anime_tab, session_tab = info_col.tabs(
        ["Metadata", "Hyetographs", "Animation", "Session"]
    )

    if ds is None:
        st.sidebar.error("Failed to load Meteorology data. Dataset is None.")
        metadata_tab.info("Unable to display metadata until the dataset loads.")
    else:
        st.sidebar.success("Meteorology data loaded successfully.")
        storm_id = st.session_state["hydromet_storm_id"]
        if storm_id is None:
            metadata_tab.info(
                "Select a Storm ID to visualize precipitation and metadata."
            )
        else:
            metadata_tab.markdown("## Storm Metadata")
            storm_meta_id = str(storm_id).zfill(3)
            storm_meta = get_stac_meta(
                f"https://stac-api.arc-apps.net/collections/72hr-events/items/{storm_meta_id}"
            )
            if storm_meta[0]:
                storm_meta = storm_meta[1]
                storm_prop = storm_meta.get("properties", {})
                metadata_tab.json(storm_prop, expanded=True)
            else:
                metadata_tab.error(
                    f"Failed to retrieve metadata for Storm ID {storm_meta_id}: {storm_meta[1]}"
                )
            compute_storm(ds, storm_id=storm_id, tab=info_col)

    # Map Position (render after potential overlay computation)
    c_lat, c_lon, zoom = get_map_pos("MET")
    with map_col:
        with st.spinner("Loading map..."):
            st.fmap = prep_metmap(
                zoom,
                c_lat,
                c_lon,
                storm_id=st.session_state["hydromet_storm_id"],
            )
            st.map_output = st.fmap.to_streamlit(height=500, bidirectional=True)

    with session_tab:
        st.markdown("## Storm Cache")
        st.json(st.session_state["storm_cache"], expanded=False)
        st.markdown("## Map State")
        last_active_drawing = st.map_output.get("last_active_drawing", None)
        st.write(last_active_drawing)
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

    with hyeto_tab:
        st.markdown("## Hyetographs")
        st.write("Select points on the map to generate hyetographs.")
        compute_hyetograph(
            ds,
            storm_id=st.session_state["hydromet_storm_id"],
            lat=st.session_state["single_event_focus_lat"],
            lon=st.session_state["single_event_focus_lon"],
            tab=hyeto_tab,
        )
        with st.expander("Plots", expanded=False, icon="📈"):
            if st.session_state["hydromet_hyetograph_data"] is not None:
                hyeto_da = st.session_state["hydromet_hyetograph_data"]
                hyeto_df = hyeto_da.to_dataframe(name="precip_in").reset_index()
                time_cols = [
                    col for col in ("abs_time", "time") if col in hyeto_df.columns
                ]
                if time_cols:
                    x_col = time_cols[0]
                else:
                    hyeto_df["timestep"] = range(len(hyeto_df))
                    x_col = "timestep"

                fig = px.line(
                    hyeto_df,
                    x=x_col,
                    y="precip_in",
                    labels={x_col: "Time", "precip_in": "Precipitation (inches)"},
                    markers=True,
                )
                fig.update_layout(margin=dict(l=20, r=20, t=20, b=20))
                st.plotly_chart(fig, use_container_width=True)
        with st.expander("Tables", expanded=False, icon="🔢"):
            if st.session_state["hydromet_hyetograph_data"] is not None:
                st.dataframe(hyeto_df)

    with anime_tab:
        st.markdown("## Storm Animation")
        st.session_state.setdefault("storm_animation_requested", False)
        st.session_state.setdefault("storm_animation_html", None)
        if ds is None:
            st.info("Dataset not loaded yet.")
        else:
            storm_id = st.session_state.get("hydromet_storm_id")
            if storm_id is None:
                st.info("Select a storm to enable animation.")
            else:
                if st.button(
                    "Generate 72-Hour Animation",
                    type="primary",
                    use_container_width=True,
                ):
                    st.session_state["storm_animation_requested"] = True
                    st.session_state["storm_animation_html"] = None
                    with st.spinner("Computing animation frames..."):
                        st.write("Computing animation frames...")
                        compute_storm_animation(ds, storm_id=storm_id)

                animation_payload = st.session_state.get("storm_animation")
                if st.session_state.get("storm_animation_html"):
                    components_html(
                        st.session_state["storm_animation_html"],
                        height=650,
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
                            st.write("Rendering animation...")
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
    hydro_met()
