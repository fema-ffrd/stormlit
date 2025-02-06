import os
from datetime import datetime

import streamlit as st


def init_session_state():
    st.session_state["session_id"] = datetime.now()
    st.session_state["init_gage_data"] = False
    st.session_state["init_storm_data"] = False
    st.session_state["init_computation_data"] = False
    st.session_state["init_map_data"] = False
    st.session_state["model_name"] = None
    st.session_state["gage_id"] = None
    st.session_state["variable"] = None
    st.session_state["realization"] = None
    st.session_state["block"] = None
    st.session_state["search_id"] = None
    st.session_state["stac_api_url"] = os.getenv("STAC_API_URL")
    st.session_state["stac_browser_url"] = os.getenv("STAC_BROWSER_URL")
    st.session_state["map_layer"] = []
    st.session_state["basemap"] = "OpenStreetMap"

    st.subbasins = None
    st.reaches = None
    st.junctions = None
    st.reservoirs = None
    st.map_output = None
    st.gages = None
    st.storms = None
    st.computation = None
    st.sel_map_obj = None
