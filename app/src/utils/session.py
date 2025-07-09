import os
from datetime import datetime
import streamlit as st


def init_session_state():
    st.session_state["session_id"] = datetime.now()
    st.session_state["stac_api_url"] = os.getenv("STAC_API_URL")
    st.session_state["stac_browser_url"] = os.getenv("STAC_BROWSER_URL")

    # Database connections
    st.session_state["pg_connected"] = False
    st.session_state["s3_connected"] = False
    st.session_state["pg_conn"] = None
    st.session_state["s3_conn"] = None

    # single event session
    st.session_state["pilot"] = None
    st.session_state["init_pilot"] = False
    st.session_state["cog_layer"] = None
    st.session_state["cog_stats"] = None
    st.session_state["cog_hist"] = None
    st.session_state["cog_hist_nbins"] = 20
    st.session_state["cog_tilejson"] = None
    st.session_state["cog_error"] = None
    st.session_state["gage_plot_type"] = None
    st.session_state["model_id"] = None
    st.session_state["single_event_focus_feature_label"] = None
    st.session_state["single_event_focus_lat"] = None
    st.session_state["single_event_focus_lon"] = None
    st.session_state["single_event_focus_zoom"] = None
    st.gage_meta_status = False
    st.gage_plot_status = False
    st.session_state["event_type"] = None
    st.session_state["calibration_event"] = None
    st.session_state["zoom_to_layer"] = None
    st.session_state["c_lat"] = None
    st.session_state["c_lon"] = None
    st.session_state["zoom"] = None
    st.session_state["zoom_to_field"] = None
    st.session_state["assets"] = None
    st.session_state["ready_to_plot_ts"] = False
    st.session_state["gage_event"] = None
    st.session_state["stochastic_event"] = None
    st.session_state["stochastic_storm"] = None
    st.session_state["block_range"] = (1, 2000)
    st.session_state["realization_id"] = None
    st.session_state["multi_event_gage_id"] = None

    # model qc session
    st.session_state["model_qc_file_path"] = None
    st.session_state["model_qc_suite"] = "FFRD"
    st.session_state["model_qc_results"] = None
    st.session_state["model_qc_status"] = True

    st.dams = None
    st.ref_lines = None
    st.ref_points = None
    st.gages = None
    st.gage_metadata = None
    st.models = None
    st.bc_lines = None
    st.subbasins = None
    st.reaches = None
    st.junctions = None
    st.reservoirs = None

    st.session_state["dams_filtered"] = None
    st.session_state["ref_points_filtered"] = None
    st.session_state["ref_lines_filtered"] = None
    st.session_state["gages_filtered"] = None
    st.session_state["models_filtered"] = None
    st.session_state["bc_lines_filtered"] = None
    st.session_state["subbasins_filtered"] = None
    st.session_state["reaches_filtered"] = None
    st.session_state["junctions_filtered"] = None
    st.session_state["reservoirs_filtered"] = None

    st.fmap = None
    st.map_output = None
    st.pilot_layers = None
    st.pilot_base_url = None
    st.sel_map_obj = None
