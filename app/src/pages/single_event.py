# module imports
from ..components.layout import render_footer
from ..configs.settings import LOG_LEVEL
from ..utils.session import init_session_state
from ..utils.stac_data import (
    init_pilot,
    get_stac_img,
    get_stac_meta,
    define_gage_data,
    define_storm_data,
    define_dam_data,
    get_ref_line_ts,
    get_ref_pt_ts,
)
from ..utils.functions import (
    prep_fmap,
    get_map_sel,
    create_st_button,
    plot_ts,
    plot_hist,
)

# standard imports
import os
import pandas as pd
from streamlit_folium import st_folium
import streamlit as st
from dotenv import load_dotenv
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")

currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
assetsDir = os.path.abspath(os.path.join(srcDir, "assets"))  # go up one level to src
load_dotenv()


def single_event():
    if "session_id" not in st.session_state:
        init_session_state()

    st.title("Single Event")
    with st.expander("About this app"):
        st.write(
            """
            This app allows you to explore single event data for both historic and stochastic simulations.
            First, please select which pilot study you would like to explore to initialize the dataset.
            Then, you may select a gage, storm rank, dam, and COG layer to begin viewing data. Selections can
            be made in either the sidebar or the map. After a selection has been made, statistics and
            analytics for that selection will be displayed to the left of the map."""
        )

    st.session_state.log_level = LOG_LEVEL

    st.sidebar.markdown("## Toolbar")
    st.session_state["pilot"] = st.sidebar.selectbox(
        "Select a Pilot Study",
        [
            "Trinity",
        ],
        index=0,
    )

    if st.session_state["init_pilot"] is False:
        with st.spinner("Initializing datasets..."):
            init_pilot(st.session_state["pilot"])
            st.session_state["init_pilot"] = True
            st.success("Complete! Pilot data is now ready for exploration.")

    st.session_state["sel_gage_id"] = st.sidebar.selectbox(
        "Select a Gage",
        ['01234567', '01234568', '01234569'],
        index=None,
    )
    st.session_state["sel_storm_rank"] = st.sidebar.selectbox(
        "Select a Storm Rank",
        [1, 2, 3, 4, 5],
        index=None,
    )
    st.session_state["sel_dam_id"] = st.sidebar.selectbox(
        "Select a Dam",
        ['Dam A', 'Dam B', 'Dam C'],
        index=None,
    )
    st.session_state["sel_cog_layer"] = st.sidebar.selectbox(
        "Select a COG Layer",
        ["Layer A","Layer B","Layer C"],
        index=None,
    )

    col3, col4 = st.columns(2)

    with col3:
        st.markdown("## Map")
        with st.spinner("Loading Map..."):
            # create a blank map
            st.map(
                zoom=6,
                use_container_width=True,
            )
    with col4:
        st.markdown("## Analytics")
        with st.expander("Gag Data"):
            st.write("view gage data analytics here")
        with st.expander("Storm Data"):
            st.write("view storm data analytics here")
        with st.expander("Dam Data"):
            st.write("view dam data analytics here")
        with st.expander("COG Data"):
            st.write("view cog data analytics here")