# module imports
from utils.particles import particles_js
from utils.session import init_session_state
from components.layout import render_footer

# standard imports
import os
from PIL import Image
import streamlit as st
from dotenv import load_dotenv
import streamlit.components.v1 as components

currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, "."))  # go up one level to src
load_dotenv()


def home_page():
    st.set_page_config(page_title="stormlit", page_icon=":rain_cloud:", layout="wide")
    if "session_id" not in st.session_state:
        init_session_state()

    st.markdown("# Stormlit")
    st.markdown("### Tools for interacting with probabilistic flood data")
    st.markdown("---")
    components.html(particles_js, scrolling=False, height=200, width=1400)

    st.sidebar.markdown("# Page Navigation")
    st.sidebar.page_link("main.py", label="Home 🏠")
    st.sidebar.page_link("pages/model_qc.py", label="Model QC")
    st.sidebar.page_link("pages/hms_results.py", label="HMS Results")
    st.sidebar.page_link("pages/ras_results.py", label="RAS Results")
    # st.sidebar.page_link("pages/all_results.py", label="All Results")
    # TESTING
    st.sidebar.page_link("pages/test_page.py", label="Test Page")

    database_link_dict = {
        "FFRD Cloud": "https://ffrd.cloud.dewberryanalytics.com/",
        "Stac-Fast API": "https://radiantearth.github.io/stac-browser/#/search/external/stac-api.arc-apps.net/",
    }

    st.sidebar.markdown("# Database ☁️")
    for link_text, link_url in database_link_dict.items():
        st.sidebar.page_link(link_url, label=link_text)

    literature_link_dict = {
        "Application of SST": "https://link.springer.com/article/10.1007/s00477-024-02853-6",
        "Evaluation of STAC": "https://www.sciencedirect.com/science/article/pii/S1364815224002913",
        "FEMA's FFRD Initiative": "https://ui.adsabs.harvard.edu/abs/2022AGUFMSY45C0653L/abstract",
    }

    st.sidebar.markdown("# Literature 📚")
    for link_text, link_url in literature_link_dict.items():
        st.sidebar.page_link(link_url, label=link_text)

    software_link_dict = {
        "FEMA-FFRD": "https://github.com/fema-ffrd",
        "Stormlit": "https://github.com/fema-ffrd/rashdf",
        "RasQC": "https://github.com/fema-ffrd/rasqc",
        "Rashdf": "https://www.rdkit.org",
        "HydroStab": "https://github.com/fema-ffrd/hydrostab",
        "Stormhub": "https://github.com/fema-ffrd/stormhub",
        "Auto-Report": "https://github.com/fema-ffrd/ffrd-auto-reports",
        "Hecstac": "https://www.hecstacl.com",
    }

    st.sidebar.markdown("# Software 💻")
    for link_text, link_url in software_link_dict.items():
        st.sidebar.page_link(link_url, label=link_text)

    st.markdown("---")

    st.markdown(
        """
        ### Summary
        *Stormlit* is a streamlit application designed for interacting with 
        probabilistic flood hazard modeling data. The *Stormlit* database represents 
        a continually updated probabilistic analysis of hydrology datasets. Composed of
        thousands of cloud compute files, these datasets directly support the Federal 
        Emergency Management Agency's (FEMA) Future of Flood Risk Data (FFRD) initiative. 
        Therefore, the core objectives of *Stormlit* are to provide an intuitive, transparent, 
        and accessible platform for exploring complex flood risk data.

        FEMA is taking steps to expand its flood mapping capabilities to equip all areas of 
        the country with risk information covering a more comprehensive range of flood hazard 
        types and frequencies. With a new hazard and risk analysis framework, FEMA aims to 
        empower communities with dynamic and credible data so they can make better risk management 
        decisions and increase their flood resilience
        """
    )

    left_col, right_col = st.columns(2)

    ffrd_path = os.path.join(srcDir, "assets", "ffrd.png")
    ffrd_img = Image.open(ffrd_path)

    right_col.image(ffrd_img, output_format="PNG")

    left_col.markdown(
        """
        ### Usage

        To the left is a dropdown main menu for navigating to 
        each page in *Stormlit*. The main menu includes the 
        following pages:

        - **Home Page:** We are here!
        - **Model QC:** Run automated quality control checks for model compliance with standard operating procedures.
        - **HMS Results:** Visualize the HEC-HMS spatial modeling components for calibration and stochastic single and multi event simulations.
        - **RAS Results:** Visualize the HEC-RAS spatial modeling components for calibration and stochastic single and multi event simulations.
        - **All Results:** View all results from the HEC-HMS and HEC-RAS models in one place.
        
        """
    )

    render_footer()


if __name__ == "__main__":
    home_page()
