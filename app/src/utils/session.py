import os
from datetime import datetime
import streamlit as st


def init_session_state():
    st.session_state["session_id"] = datetime.now()
    st.session_state["stac_api_url"] = os.getenv("STAC_API_URL")
    st.session_state["stac_browser_url"] = os.getenv("STAC_BROWSER_URL")

    # PG database connection
    st.session_state["db_connected"] = False
    st.session_state["db_conn"] = None

    # single event session
    st.session_state["pilot"] = None
    st.session_state["init_pilot"] = False
    st.session_state["sel_basin_id"] = None
    st.session_state["sel_gage_id"] = None
    st.session_state["sel_storm_rank"] = None
    st.session_state["sel_dam_id"] = None
    st.session_state["sel_cog_layer"] = None
    st.session_state["cog_stats"] = None
    st.session_state["sel_cmap"] = "rainbow"
    st.session_state["gage_plot_type"] = None
    st.session_state["sel_ref_line_id"] = None
    st.session_state["sel_ref_point_id"] = None
    st.gage_meta_status = False
    st.gage_plot_status = False
    st.session_state["event_type"] = None
    st.session_state["calibration_event"] = None
    st.session_state["stochastic_event"] = None
    st.session_state["zoom_to_layer"] = None
    st.session_state["c_lat"] = None
    st.session_state["c_lon"] = None
    st.session_state["zoom"] = None
    st.session_state["zoom_to_field"] = None

    # model qc session
    st.session_state["model_qc_file_path"] = None
    st.session_state["model_qc_suite"] = "FFRD"
    st.session_state["model_qc_results"] = None
    st.session_state["model_qc_status"] = True

    st.basins = None
    st.reservoirs = None
    st.fmap = None
    st.map_output = None
    st.gages = None
    st.dams = None
    st.storms = None
    st.pilot_layers = None
    st.pilot_base_url = None
    st.sel_map_obj = None