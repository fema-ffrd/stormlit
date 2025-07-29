# module imports
from utils.session import init_session_state
from db.utils import create_pg_connection, create_s3_connection

# standard imports
import os
import streamlit as st
import pandas as pd
import geopandas as gpd
from dotenv import load_dotenv
from urllib.parse import urljoin
import logging

currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
assetsDir = os.path.abspath(os.path.join(srcDir, "assets"))  # go up one level to src
load_dotenv()

logger = logging.getLogger(__name__)


def hms_summary():
    """
    Main function to render the HMS summary page.
    """
    st.set_page_config(page_title="stormlit", page_icon=":rain_cloud:", layout="wide")
    if "session_id" not in st.session_state:
        init_session_state()

    st.title("HMS Summary")

    # Sidebar configuration
    st.sidebar.markdown("# Page Navigation")
    st.sidebar.page_link("main.py", label="Home 🏠")
    st.sidebar.page_link("pages/model_qc.py", label="Model QC")
    st.sidebar.page_link("pages/hms_results.py", label="HMS Results")
    st.sidebar.page_link("pages/ras_results.py", label="RAS Results")
    st.sidebar.page_link("pages/all_results.py", label="All Results")
    st.sidebar.page_link("pages/hms_summary.py", label="HMS Summary")

    if st.session_state["pg_connected"] is False:
        st.session_state["pg_conn"] = create_pg_connection()
    if st.session_state["s3_connected"] is False:
        st.session_state["s3_conn"] = create_s3_connection()


if __name__ == "__main__":
    hms_summary()
