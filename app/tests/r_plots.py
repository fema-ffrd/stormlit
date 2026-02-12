# module imports
from src.utils.r_server import get_r_plot

# standard imports
import os
import json
from dotenv import load_dotenv
import logging

# third party imports
import streamlit as st
import plotly.graph_objects as go

currDir = os.path.dirname(os.path.realpath(__file__))
dataDir = os.path.join(currDir, "data")
load_dotenv()

logger = logging.getLogger(__name__)


def test_r_plots():
    st.set_page_config(page_title="stormlit", page_icon=":rain_cloud:", layout="wide")

    st.title("R Plots Test Page")

    test_plot_file = os.path.join(dataDir, "json", "flow-example.json")
    if os.path.exists(test_plot_file):
        with open(test_plot_file, "r") as f:
            flow_data = json.load(f)

        # Get cleaned JSON from R service
        plot_json = get_r_plot("flows", flow_data)

        # Create Plotly figure from cleaned data
        fig = go.Figure(
            data=plot_json.get("data", []), layout=plot_json.get("layout", {})
        )

        # Use st.plotly_chart for full interactivity (click events, etc.)
        plot_selection = st.plotly_chart(
            fig, width="stretch", on_select="rerun", selection_mode="lasso"
        )

        # Handle plot selection
        if len(plot_selection["selection"]["points"]) > 0:
            selected_points = plot_selection["selection"]["points"]
            st.write("Selected points:", selected_points)
        else:
            st.write("No points selected.")
            st.write(plot_selection)


if __name__ == "__main__":
    test_r_plots()
