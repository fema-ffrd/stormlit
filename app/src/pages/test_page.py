# module imports
from utils.session import init_session_state
from utils.r_server import get_flow_plot

# standard imports
import os
import json
from dotenv import load_dotenv
import logging

# third party imports
import streamlit as st
import plotly.graph_objects as go

currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
assetsDir = os.path.abspath(os.path.join(srcDir, "assets"))  # go up one level to src
load_dotenv("/workspace/app/.env")

logger = logging.getLogger(__name__)


def test_results():
    st.set_page_config(page_title="stormlit", page_icon=":rain_cloud:", layout="wide")
    if "session_id" not in st.session_state:
        init_session_state()

    st.title("Test Results")

    # Sidebar configuration
    st.sidebar.markdown("# Page Navigation")
    st.sidebar.page_link("main.py", label="Home 🏠")
    st.sidebar.page_link("pages/model_qc.py", label="Model QC")
    st.sidebar.page_link("pages/hms_results.py", label="HMS Results")
    st.sidebar.page_link("pages/ras_results.py", label="RAS Results")
    # st.sidebar.page_link("pages/all_results.py", label="All Results")
    # TESTING
    st.sidebar.page_link("pages/test_page.py", label="Test Page")

    test_plot_file = "/workspace/app/tests/flow-example.json"
    if os.path.exists(test_plot_file):
        with open(test_plot_file, "r") as f:
            flow_data = json.load(f)

        # Get cleaned JSON from R service
        plot_json = get_flow_plot(flow_data)

        # Create Plotly figure from cleaned data
        fig = go.Figure(
            data=plot_json.get("data", []), layout=plot_json.get("layout", {})
        )

        # Use st.plotly_chart for full interactivity (click events, etc.)
        plot_selection = st.plotly_chart(
            fig, use_container_width=True, on_select="rerun", selection_mode="lasso"
        )

        # Handle plot selection
        if len(plot_selection["selection"]["points"]) > 0:
            selected_points = plot_selection["selection"]["points"]
            st.write("Selected points:", selected_points)
        else:
            st.write("No points selected.")
            st.write(plot_selection)


if __name__ == "__main__":
    test_results()
