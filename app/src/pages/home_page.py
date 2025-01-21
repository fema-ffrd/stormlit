# standard imports
import os
import sys
from PIL import Image
import streamlit as st
from dotenv import load_dotenv
import streamlit.components.v1 as components

# global variables
currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
sys.path.append(srcDir)
load_dotenv()

# custom imports
from utils.particles import particles_js
from utils.functions import create_st_button
from utils.session import init_session_state
from components.layout import render_footer


def home_page():
    if "session_id" not in st.session_state:
        init_session_state()

    st.markdown("# Stormlit")
    st.markdown("### A tool for interacting with probabilistic flood data")
    st.markdown("---")
    components.html(particles_js, scrolling=False, height=200, width=1400)

    database_link_dict = {
        "FFRD Cloud": "https://ffrd.cloud.dewberryanalytics.com/",
    }

    st.sidebar.markdown("## Database")
    for link_text, link_url in database_link_dict.items():
        create_st_button(link_text, link_url, st_col=st.sidebar)

    literature_link_dict = {
        "Application of SST": "https://link.springer.com/article/10.1007/s00477-024-02853-6",
        "Evaluation of STAC": "https://www.sciencedirect.com/science/article/pii/S1364815224002913",
        "FEMA's FFRD Initiative": "https://ui.adsabs.harvard.edu/abs/2022AGUFMSY45C0653L/abstract",
    }

    st.sidebar.markdown("## Literature")
    for link_text, link_url in literature_link_dict.items():
        create_st_button(link_text, link_url, st_col=st.sidebar)

    software_link_dict = {
        "FEMA-FFRD": "https://github.com/fema-ffrd",
        "Stormlit": "https://github.com/fema-ffrd/rashdf",
        "Rashdf": "https://www.rdkit.org",
        "Stormhub": "https://github.com/fema-ffrd/stormhub",
        "Auto-Report": "https://github.com/fema-ffrd/ffrd-auto-reports",
        "Hecstac": "https://www.hecstacl.com",
    }

    st.sidebar.markdown("## Software")
    link_1_col, link_2_col, link_3_col = st.sidebar.columns(3)

    i = 0
    link_col_dict = {0: link_1_col, 1: link_2_col, 2: link_3_col}
    for link_text, link_url in software_link_dict.items():
        st_col = link_col_dict[i]
        i += 1
        if i == len(link_col_dict.keys()):
            i = 0

        create_st_button(link_text, link_url, st_col=st_col)

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

        To the left, is a dropdown main menu for navigating to 
        each page in *Stormlit*. The main menu includes the 
        following pages:

        - **Home Page:** We are here!
        - **Load Data:** Initialize the *Stormlit* database
        - **View Gages:** Explore multi-event gage results
        - **View Storms:** Visualize storm data and SST coverage
        """
    )

    render_footer()
