# module imports
from ..components.layout import render_footer
from ..configs.settings import LOG_LEVEL
from ..utils.session import init_session_state
from ..utils.stac_data import init_map_data
from ..utils.functions import prep_fmap, get_map_sel


# standard imports
import os
from streamlit_folium import st_folium
import streamlit as st
from dotenv import load_dotenv
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")

# global variables
map_layer_dict = {
    "Subbasins": "https://duwamish-pilot.s3.amazonaws.com/stac/Subbasin.geojson",
    "Reachs": "https://duwamish-pilot.s3.amazonaws.com/stac/Reach.geojson",
    "Junctions": "https://duwamish-pilot.s3.amazonaws.com/stac/Junction.geojson",
    "Reservoirs": "https://duwamish-pilot.s3.amazonaws.com/stac/Reservoir.geojson",
}

currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
load_dotenv()


def view_map():
    if "session_id" not in st.session_state:
        init_session_state()

    st.session_state.log_level = LOG_LEVEL

    if st.session_state["init_map_data"] is False:
        with st.spinner("Initializing datasets..."):
            init_map_data(map_layer_dict)
            st.session_state["init_map_data"] = True
            st.balloons()
            st.success("Complete! Map data is now ready for exploration.")

    st.markdown("## Map Viewer")
    st.write("""Select one ore multiple map layers from the sidebar to plot on the map. 
             Afterwards, you may then select objects from the map to view additional information below.""")

    st.sidebar.markdown("## Toolbar")
    st.session_state["map_layer"] = st.sidebar.multiselect(
        "Select Map Layer(s)", list(map_layer_dict.keys()),
        default=None
    )
    st.session_state["basemap"] = st.sidebar.selectbox(
        "Select Basemap", ["OpenStreetMap", "ESRI Satellite", "Google Satellite"],
        index=0
    )

    if len(st.session_state["map_layer"]) > 0:
        # Refresh the map
        fmap, feature_group = prep_fmap(st.session_state["map_layer"],
                                        st.session_state["basemap"])
        # Display the map
        st.map_output = st_folium(fmap,
                                    key="base_map",
                                    height=800,
                                    feature_group_to_add=feature_group,
                                    use_container_width=True)
    else:
        st.warning("Please first select a map layer to view.")

    if st.map_output is not None:
        if st.map_output["last_object_clicked_tooltip"] is not None:
            st.sel_map_obj = get_map_sel(st.map_output)
            st.subheader("Selected Object Information")
            st.dataframe(st.sel_map_obj.drop(columns=["geometry"]))
        
    render_footer()
