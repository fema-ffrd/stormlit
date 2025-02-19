"""
https://fema-ffrd.github.io/stac-browser/#/external/duwamish-pilot.s3.amazonaws.com/stac/duwamish/collection.json?.language=en
"""

# module imports
from ..components.layout import render_footer
from ..configs.settings import LOG_LEVEL
from ..utils.session import init_session_state
from ..utils.stac_data import init_map_data
from ..utils.functions import prep_fmap, get_map_sel, create_st_button
from ..utils.nwis_api import select_usgs_gages, get_nwis_streamflow
from ..utils.plotting import create_time_series_plot


# standard imports
import os
from streamlit_folium import st_folium
import geopandas as gpd
import streamlit as st
from dotenv import load_dotenv
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")

currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
assetsDir = os.path.abspath(os.path.join(srcDir, "assets"))  # go up one level to src
load_dotenv()

# global variables
map_layer_dict = {
    "Subbasins": "https://duwamish-pilot.s3.amazonaws.com/stac/Subbasin.geojson",
    "Reaches": "https://duwamish-pilot.s3.amazonaws.com/stac/Reach.geojson",
    "Junctions": "https://duwamish-pilot.s3.amazonaws.com/stac/Junction.geojson",
    "Reservoirs": "https://duwamish-pilot.s3.amazonaws.com/stac/Reservoir.geojson",
}


def view_map():
    if "session_id" not in st.session_state:
        init_session_state()

    st.session_state.log_level = LOG_LEVEL

    if st.session_state["init_map_data"] is False:
        with st.spinner("Initializing datasets..."):
            init_map_data(map_layer_dict)
            st.session_state["init_map_data"] = True
            st.success("Complete! Map data is now ready for exploration.")

    st.sidebar.markdown("## Toolbar")
    st.session_state["basemap"] = st.sidebar.selectbox(
        "Select Basemap",
        ["OpenStreetMap", "ESRI Satellite", "Google Satellite"],
        index=0,
    )
    st.session_state["gage_param"] = st.sidebar.selectbox(
        "Select Gage Parameter",
        ["Streamflow", "Stage", "Precipitation"],
        index=0,
    )
    st.session_state["data_type"] = st.sidebar.selectbox(
        "Select Data Type",
        ["Daily", "Instantaneous"],
        index=0,
    )
    st.session_state["data_status"] = st.sidebar.selectbox(
        "Select Data Status",
        ["Active", "All"],
        index=0,
    )

    # add download buttons for each selected map layer
    st.subheader("Download Map Layers")
    col1, col2, col3, col4 = st.columns(4)
    create_st_button(
        "Subbasins", map_layer_dict["Subbasins"], hover_color="#1c66e8", st_col=col1
    )
    create_st_button(
        "Reaches", map_layer_dict["Reaches"], hover_color="#e8371c", st_col=col2
    )
    create_st_button(
        "Junctions", map_layer_dict["Junctions"], hover_color="#47c408", st_col=col3
    )
    create_st_button(
        "Reservoirs", map_layer_dict["Reservoirs"], hover_color="#1bbdde", st_col=col4
    )

    st.markdown("## Map Viewer")
    st.write("""Select objects from the map to view their attributes. 
             You may quickly toggle layers on and off using the layer control located 
             in the upper right corner of the map. Select a subbasin to view all available
             USGS gages. Afterwards, you may select a gage from the selected subbasin
             to view Period of Record (POR).
             """)
    # Display the map and map layers
    with st.spinner("Loading Map..."):
        st.fmap = prep_fmap(list(map_layer_dict.keys()), st.session_state["basemap"])
        st.map_output = st_folium(
            st.fmap,
            key="new_map",
            height=500,
            use_container_width=True,
        )
    # Display the selected object information from the map
    if st.map_output is not None:
        if st.map_output["last_object_clicked_tooltip"] is not None:
            st.sel_map_obj = get_map_sel(st.map_output)
            st.subheader("Selected Map Information")
            st.dataframe(st.sel_map_obj.drop(columns=["geometry"]))
            # query the NWIS API for gages within the selected geometry
            if "Subbasins" in st.sel_map_obj["layer"].values:
                st.gage_df = select_usgs_gages(
                    st.sel_map_obj,
                    parameter=st.session_state["gage_param"],
                    realtime=st.session_state["data_status"],
                    data_type=st.session_state["data_type"],
                )
    # Display the gage information within the selected subbasin
    if st.map_output is not None:
        if st.map_output["last_object_clicked_tooltip"] is not None:
            if "Subbasins" in st.sel_map_obj["layer"].values:
                st.subheader("USGS Gages within Selected Subbasin")
                if isinstance(st.gage_df, str):
                    st.error(st.gage_df)
                else:
                    st.dataframe(st.gage_df.drop(columns=["geometry"]))
    if isinstance(st.gage_df, gpd.GeoDataFrame):
        st.session_state["gage_id"] = st.sidebar.selectbox(
            "Select a USGS Gage",
            st.gage_df["site_no"].values,
            index=None,
        )
    # Display the Period of Record (POR) for the selected gage
    if st.session_state["gage_id"] is not None:
        if isinstance(st.gage_df, gpd.GeoDataFrame):
            filtered_df = st.gage_df[
                st.gage_df["site_no"] == st.session_state["gage_id"]
            ]
            dates = (
                filtered_df["begin_date"].values[0],
                filtered_df["end_date"].values[0],
            )
            st.gage_df_por = get_nwis_streamflow(
                st.session_state["gage_id"], dates, freq=st.session_state["data_type"]
            )
            # Create the Plotly figure
            fig = create_time_series_plot(st.gage_df_por)
            # Display the Plotly figure in Streamlit
            st.plotly_chart(fig)
    # Display the session state
    with st.expander("View Session State"):
        st.write(st.session_state)
    render_footer()
