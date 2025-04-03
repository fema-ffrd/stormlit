import os
from datetime import datetime

import streamlit as st


def init_session_state():
    st.session_state["session_id"] = datetime.now()
    st.session_state["pilot"] = None
    st.session_state["init_gage_data"] = False
    st.session_state["init_pilot"] = False
    st.session_state["init_storm_data"] = False
    st.session_state["init_computation_data"] = False
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
    st.session_state["data_type"] = "Daily"
    st.session_state["data_status"] = "All"
    st.session_state["gage_param"] = "Streamflow"
    st.session_state["gage_id"] = None
    st.session_state["basin_name"] = None
    st.session_state["storm_rank"] = None
    st.session_state["cog_layer"] = None

    st.basins = None
    st.reservoirs = None
    st.fmap = None
    st.map_output = None
    st.gages = None
    st.dams = None
    st.storms = None
    st.computation = None
    st.gage_df = None
    st.sel_map_obj = None
    st.sel_gage = None
    st.gage_df_por = None
    st.pilot_layers = None
    st.pilot_base_url = None
    st.port = None
