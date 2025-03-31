# module imports
from ..components.layout import render_footer
from ..configs.settings import LOG_LEVEL
from ..utils.session import init_session_state
from ..utils.stac_data import (
    init_pilot,
    get_stac_img,
    get_stac_meta,
    define_gage_data,
    define_storm_data,
    define_dam_data,
    get_ref_line_ts,
    get_ref_pt_ts,
)
from ..utils.functions import (prep_fmap,
                               get_map_sel,
                               create_st_button,
                               init_cog,
                               kill_cog,
                               plot_ts
)

# standard imports
import os
from streamlit_folium import st_folium
import streamlit as st
from dotenv import load_dotenv
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")

currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
assetsDir = os.path.abspath(os.path.join(srcDir, "assets"))  # go up one level to src
load_dotenv()


def view_map():
    if "session_id" not in st.session_state:
        init_session_state()

    st.session_state.log_level = LOG_LEVEL

    st.sidebar.markdown("## Toolbar")
    st.session_state["pilot"] = st.sidebar.selectbox(
        "Select a Pilot Study",
        [
            "Trinity",
        ],
        index=0,
    )

    if st.session_state["init_pilot"] is False:
        with st.spinner("Initializing datasets..."):
            init_pilot(st.session_state["pilot"])
            st.session_state["init_pilot"] = True
            st.success("Complete! Pilot data is now ready for exploration.")

    st.session_state["basemap"] = st.sidebar.selectbox(
        "Select a Basemap",
        ["OpenStreetMap", "ESRI Satellite", "Google Satellite"],
        index=0,
    )

    st.session_state["gage_plot"] = st.sidebar.selectbox(
        "Select a Gage Plot Type",
        ["Flow Stats", "AMS", "AMS Seasons", "AMS LP3"],
        index=0,
    )
    storm_ranks = sorted(st.storms["rank"].unique())
    st.session_state["storm_rank"] = st.sidebar.selectbox(
        "Select a Storm Rank",
        storm_ranks,
        index=None,
    )
    basin_names = sorted(st.basins["NAME"].unique())
    st.session_state["basin_name"] = st.sidebar.selectbox(
        "Select a Basin",
        basin_names,
        index=None,
    )
    cog_names = sorted(list(st.cog_layers.keys()))
    st.session_state["cog_layer"] = st.sidebar.selectbox(
        "Select a COG Layer",
        cog_names,
        index=None,
    )

    # add download buttons for each selected map layer
    st.subheader("Download Map Layers")
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    create_st_button(
        "Basins", st.pilot_layers["Basins"], background_color="#1e90ff", st_col=col1
    )
    col1.write("Polygons")
    create_st_button(
        "Dams", st.pilot_layers["Dams"], background_color="#e32636", st_col=col2
    )
    col2.write("Circles")
    create_st_button(
        "Gages", st.pilot_layers["Gages"], background_color="#32cd32", st_col=col3
    )
    col3.write("Circles")
    create_st_button(
        "Storms", st.pilot_layers["Storms"], background_color="#ed9121", st_col=col4
    )
    col4.write("Circles")
    create_st_button(
        "Reference Lines",
        st.pilot_layers["Reference Lines"],
        background_color="#1e90ff",
        st_col=col5,
    )
    col5.write("Lines")
    create_st_button(
        "Reference Points",
        st.pilot_layers["Reference Points"],
        background_color="#1e90ff",
        st_col=col6,
    )
    col6.write("Markers")

    st.markdown("## Map Viewer")
    st.write("""Select objects from the map to view their attributes. 
             You may quickly toggle layers on and off using the layer control located 
             in the upper right corner of the map. Select a subbasin to view all available
             USGS gages. Afterwards, you may select a gage from the selected subbasin
             to view Period of Record (POR).
             """)
    # Display the map and map layers
    with st.spinner("Loading Map..."):
        st.fmap = prep_fmap(
            list(st.pilot_layers.keys()),
            st.session_state["basemap"],
            st.session_state["basin_name"],
            st.session_state["storm_rank"],
        )
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

    if st.sel_map_obj is not None:
        # Display the gage information if a gage is selected
        if "Gages" in st.sel_map_obj["layer"].values:
            gage_id = st.sel_map_obj["site_no"].values[0]
            gage_meta_url = define_gage_data(gage_id)["Metadata"]
            gage_meta_status, gage_meta = get_stac_meta(gage_meta_url)
            gage_plot_url = define_gage_data(gage_id)[st.session_state["gage_plot"]]
            gage_plot_status, gage_plot_img = get_stac_img(gage_plot_url)
            # display the metadata
            if gage_meta_status:
                with st.expander("View Metadata"):
                    st.write(gage_meta["properties"])
            else:
                st.error("Error: Unable to retrieve the metadata.")
                st.write(f"URL: {gage_meta_url}")
            # display the img
            if gage_plot_status:
                st.write(f"""Collection of USGS streamflow gages in the {st.session_state["pilot"]}
                          Watershed containing more than 15 years of annual maxima observations.
                          Note that the LP-III computations do not include regional skew. This is
                          a provisional collection, pending added datasets curated by engineers
                          developing the hydrologic model.
                         """)
                st.image(gage_plot_img, use_container_width=True)
            else:
                st.error("Error: Unable to retrieve the plot.")
                st.write(f"URL: {gage_plot_img}")
        # Display the storm information if a storm is selected
        elif "Storms" in st.sel_map_obj["layer"].values:
            storm_rank = int(st.sel_map_obj["rank"].values[0])
            storm_meta_url = define_storm_data(storm_rank)["Metadata"]
            storm_meta_status, storm_meta = get_stac_meta(storm_meta_url)
            # display the metadata
            if storm_meta_status:
                storm_plot_url = storm_meta["assets"]["thumbnail"]["href"]
                storm_plot_status, storm_plot_img = get_stac_img(storm_plot_url)
                with st.expander("View Metadata"):
                    st.write(storm_meta["properties"])
            else:
                st.error("Error: Unable to retrieve the metadata.")
                st.write(f"URL: {storm_meta_url}")
            # display the img
            if storm_meta_status and storm_plot_status:
                st.write(f"""Collection of the top storms developed in the {st.session_state["pilot"]}
                            Watershed for a 72-hour storm period.
                            """)
                st.image(storm_plot_img, use_container_width=True)
            else:
                st.error("Error: Unable to retrieve the plot.")
                st.write(f"URL: {storm_plot_img}")
        # Display the dam information if a dam is selected
        elif "Dams" in st.sel_map_obj["layer"].values:
            dam_id = st.sel_map_obj["id"].values[0]
            dam_meta_url = define_dam_data(dam_id)["Metadata"]
            dam_meta_status, dam_meta = get_stac_meta(dam_meta_url)
            # display the metadata
            if dam_meta_status:
                # update the href in each asset to point to the full url for downloading
                for key, asset in dam_meta["assets"].items():
                    asset['href'] = f"{st.pilot_base_url}/dams/non-usace/{dam_id}/{key}"
                with st.expander("View Metadata"):
                    st.write(dam_meta["assets"])
            else:
                st.error("Error: Unable to retrieve the metadata.")
                st.write(f"URL: {dam_meta_url}")
        elif "Reference Lines" in st.sel_map_obj["layer"].values:
            ref_line_id = st.sel_map_obj["id"].values[0]
            st.write(f"Selected Reference Line: {ref_line_id}")
            ref_line_ts = get_ref_line_ts(ref_line_id)
            col1, col2 = st.columns(2)
            with col1:
                plot_ts(ref_line_ts, "water_surface")
            with col2:
                plot_ts(ref_line_ts, "flow")
        elif "Reference Points" in st.sel_map_obj["layer"].values:
            ref_point_id = st.sel_map_obj["id"].values[0]
            st.write(f"Selected Reference Point: {ref_point_id}")
            ref_pt_ts = get_ref_pt_ts(ref_point_id)
            col1, col2 = st.columns(2)
            with col1:
                plot_ts(ref_pt_ts, "water_surface")
            with col2:
                plot_ts(ref_pt_ts, "velocity")
        elif "Basins" in st.sel_map_obj["layer"].values:
            basin_id = st.sel_map_obj["HUC8"].values[0]
            basin_gdf = st.basins[st.basins["HUC8"] == basin_id]
            basin_bbox = basin_gdf["bbox"].values[0]
            basin_bbox = [float(coord) for coord in basin_bbox.split(",")]
            st.dataframe(basin_gdf.drop(columns=["geometry"]))
        else:
            pass

    if st.session_state["cog_layer"] is not None:
        cog_s3uri = st.cog_layers[st.session_state["cog_layer"]]
        st.subheader("View Cloud Optimized GeoTIFF (COG)")
        col1, col2 = st.columns(2)
        with col1:
            st.write("Click the button to visualize the model results.")
            if st.button("View COG", key="view_cog"):
                # st.session_state["cog_url"], st.cog_process = init_cog(cog_s3uri)
                init_cog(cog_s3uri)
        with col2:
            st.write("Click the button to terminate the COG server.")
            if st.button("Kill COG", key="kill_cog"):
                kill_cog()
                # st.session_state["cog_url"] = None
                # st.session_state["init_cog"] = False

    # Display the session state
    with st.expander("View Session State"):
        st.write(st.session_state)
    render_footer()
