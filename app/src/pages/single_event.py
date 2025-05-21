# module imports
from components.layout import render_footer
from configs.settings import LOG_LEVEL
from utils.session import init_session_state
from utils.stac_data import (
    init_pilot,
    define_gage_data,
    define_storm_data,
    define_dam_data,
    get_stac_img,
    get_stac_meta,
    get_ref_line_ts,
    get_ref_pt_ts,
)
from utils.functions import (
    get_map_sel,
    get_map_pos,
    prep_fmap,
    plot_hist,
    plot_ts,
)

# standard imports
import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
import warnings
from streamlit_folium import st_folium
from streamlit_option_menu import option_menu

# Suppress warnings
warnings.filterwarnings("ignore")

currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
assetsDir = os.path.abspath(os.path.join(srcDir, "assets"))  # go up one level to src
load_dotenv()


def single_event():
    st.set_page_config(page_title="stormlit", page_icon=":rain_cloud:", layout="wide")
    if "session_id" not in st.session_state:
        init_session_state()

    st.title("Single Event")
    with st.expander("About this app"):
        st.write(
            """
            This app allows you to explore single event data for both historic and stochastic simulations.
            First, please select which pilot study you would like to explore to initialize the dataset.
            Then, you may select a gage, storm rank, dam, and COG layer to begin viewing data. Selections can
            be made in either the sidebar or the map. After a selection has been made, statistics and
            analytics for that selection will be displayed to the right of the map."""
        )

    st.session_state.log_level = LOG_LEVEL

    st.sidebar.markdown("# Page Navigation")
    st.sidebar.page_link("main.py", label="Home 🏠")
    st.sidebar.page_link("pages/model_qc.py", label="Model QC 📋")
    st.sidebar.page_link("pages/single_event.py", label="Single Event Viewer ⛈️")

    st.sidebar.markdown("## Select Study")
    st.session_state["pilot"] = st.sidebar.selectbox(
        "Select a Pilot Study",
        [
            "Trinity",
        ],
        index=0,
    )
    st.sidebar.markdown("---")

    if st.session_state["init_pilot"] is False:
        with st.spinner("Initializing datasets..."):
            init_pilot(st.session_state["pilot"])
            st.session_state["init_pilot"] = True
            st.success("Complete! Pilot data is now ready for exploration.")

    st.sidebar.markdown("## Select Event")
    st.session_state["event_type"] = st.sidebar.radio(
        "Select from",
        ["Calibration Events", "Stochastic Events"],
        index=0,
    )

    if st.session_state["event_type"] == "Calibration Events":
        st.session_state["calibration_event"] = st.sidebar.selectbox(
            "Select from",
            ["Jan1996", "Aug2017", "July2020", "Aug2021"],
            index=None,
        )
    else:
        st.session_state["stochastic_event"] = st.sidebar.selectbox(
            "Select from",
            ["Stochastic Event 1", "Stochastic Event 2", "Stochastic Event 3"],
            index=None,
        )

    selected_layer = option_menu(
        menu_title="Map Layers",
        options=[
            "Basins",
            "Gages",
            "Storms",
            "Dams",
            "COGs",
            "Reference Lines",
            "Reference Points",
        ],
        icons=[
            "bounding-box",
            "moisture",
            "cloud-drizzle",
            "triangle",
            "layers",
            "slash-lg",
            "dot",
        ],
        orientation="horizontal",
        menu_icon="map",
        default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "#fafafa"},
            "icon": {"color": "#0f0f0f", "font-size": "18px"},
            "nav-link": {
                "font-size": "18px",
                "text-align": "left",
                "margin": "0px",
                "--hover-color": "#2051ba",
            },
            "nav-link-selected": {"background-color": "#2051ba"},
        },
    )

    container1 = st.container()
    col1, col2 = container1.columns(2)

    # Get the map position based on the selection
    with container1:
        if (
            st.session_state["zoom_to_layer"] is not None
            and st.session_state["zoom_to_field"] is not None
        ):
            c_lat, c_lon, zoom = get_map_pos(
                st.session_state["zoom_to_layer"],
                st.session_state["zoom_to_field"],
            )
        # Default map position
        else:
            c_lat, c_lon, zoom = get_map_pos(
                "Study Area",
                None,
            )

    with col1:
        with st.spinner("Loading Map..."):
            st.fmap = prep_fmap(
                list(st.pilot_layers.keys()),
                st.session_state["sel_cog_layer"],
                st.session_state["sel_cmap"],
            )
            st.map_output = st_folium(
                st.fmap,
                center=[c_lat, c_lon],
                zoom=zoom,
                key="new_map",
                height=500,
                use_container_width=True,
            )

    if selected_layer == "Basins":
        st.session_state["zoom_to_layer"] = selected_layer
        basin_id_list = sorted(st.basins["NAME"].unique().tolist())
        st.session_state["sel_basin_id"] = col2.selectbox(
            "Select a Basin by Name",
            basin_id_list,
            index=None,
        )
        st.session_state["zoom_to_field"] = st.session_state["sel_basin_id"]
        if st.session_state["sel_basin_id"] is not None:
            if col2.button("Zoom to Basin", key="zoom_to_basin"):
                st.rerun()

    elif selected_layer == "Gages":
        st.session_state["zoom_to_layer"] = selected_layer
        gage_id_list = sorted(st.gages["site_no"].unique().tolist())
        st.session_state["sel_gage_id"] = col2.selectbox(
            "Select a Gage by ID",
            gage_id_list,
            index=None,
        )
        st.session_state["zoom_to_field"] = st.session_state["sel_gage_id"]
        if st.session_state["sel_gage_id"] is not None:
            if col2.button("Zoom to Gage", key="zoom_to_gage"):
                st.rerun()
    elif selected_layer == "Storms":
        st.session_state["zoom_to_layer"] = selected_layer
        storm_rank_list = sorted(st.storms["rank"].unique().tolist())
        st.session_state["sel_storm_rank"] = col2.selectbox(
            "Select a Storm by Rank",
            storm_rank_list,
            index=None,
        )
        st.session_state["zoom_to_field"] = st.session_state["sel_storm_rank"]
        if st.session_state["sel_storm_rank"] is not None:
            if col2.button("Zoom to Storm", key="zoom_to_storm"):
                st.rerun()
    elif selected_layer == "Dams":
        st.session_state["zoom_to_layer"] = selected_layer
        dam_id_list = sorted(st.dams["id"].unique().tolist())
        st.session_state["sel_dam_id"] = col2.selectbox(
            "Select a Dam by ID",
            dam_id_list,
            index=None,
        )
        st.session_state["zoom_to_field"] = st.session_state["sel_dam_id"]
        if st.session_state["sel_dam_id"] is not None:
            if col2.button("Zoom to Dam", key="zoom_to_dam"):
                st.rerun()
    elif selected_layer == "COGs":
        st.session_state["zoom_to_layer"] = selected_layer
        cog_id_list = sorted(list(st.cog_layers.keys()))
        st.session_state["sel_cog_layer"] = col2.selectbox(
            "Select a COG by Name",
            cog_id_list,
            index=None,
        )
        st.session_state["zoom_to_field"] = st.session_state["sel_cog_layer"]
        if st.session_state["sel_cog_layer"] is not None:
            if col2.button("Zoom to COG", key="zoom_to_cog"):
                st.rerun()
    elif selected_layer == "Reference Lines":
        st.session_state["zoom_to_layer"] = selected_layer
        ref_line_id_list = sorted(st.ref_lines["id"].unique().tolist())
        st.session_state["sel_ref_line_id"] = col2.selectbox(
            "Select a Reference Line by ID",
            ref_line_id_list,
            index=None,
        )
        st.session_state["zoom_to_field"] = st.session_state["sel_ref_line_id"]
        if st.session_state["sel_ref_line_id"] is not None:
            if col2.button("Zoom to Line", key="zoom_to_line"):
                st.rerun()
    elif selected_layer == "Reference Points":
        st.session_state["zoom_to_layer"] = selected_layer
        ref_point_id_list = sorted(st.ref_points["id"].unique().tolist())
        st.session_state["sel_ref_point_id"] = col2.selectbox(
            "Select a Reference Point by ID",
            ref_point_id_list,
            index=None,
        )
        st.session_state["zoom_to_field"] = st.session_state["sel_ref_point_id"]
        if st.session_state["sel_ref_point_id"] is not None:
            # Select which layer to zoom to in the map
            if col2.button("Zoom to Point", key="zoom_to_point"):
                st.rerun()

    # Display the selected object information from the map
    if st.map_output is not None:
        if st.map_output["last_object_clicked_tooltip"] is not None:
            st.sel_map_obj = get_map_sel(st.map_output)
            st.subheader("Selected Map Information")

    col3, col4 = container1.columns(2)

    if selected_layer == "Basins":
        col2.write("Download the map layer")
        col2.link_button(
            "Basins",
            st.pilot_layers["Basins"],
        )
        # Basin Map Selection
        if st.sel_map_obj is not None:
            if "Basins" in st.sel_map_obj["layer"].values:
                basin_id = st.sel_map_obj["HUC8"].values[0]
                basin_gdf = st.basins[st.basins["HUC8"] == basin_id]
                col2.dataframe(basin_gdf.drop(columns=["geometry"]))
        # Basin Dropdown Selection
        elif st.session_state["sel_basin_id"] is not None:
            basin_id = st.session_state["sel_basin_id"]
            basin_gdf = st.basins[st.basins["NAME"] == basin_id]
            col2.dataframe(basin_gdf.drop(columns=["geometry"]))

    elif selected_layer == "Gages":
        col2.write("Download the map layer")
        col2.link_button("Gages", st.pilot_layers["Gages"])
        st.session_state["gage_plot_type"] = col2.selectbox(
            "Select a Gage Plot Type",
            ["Flow Stats", "AMS", "AMS Seasons", "AMS LP3"],
            index=0,
        )
        # Gage Map Selection
        if st.sel_map_obj is not None and "Gages" in st.sel_map_obj["layer"].values:
            gage_id = st.sel_map_obj["site_no"].values[0]
            gage_meta_url = define_gage_data(gage_id)["Metadata"]
            gage_meta_status, gage_meta = get_stac_meta(gage_meta_url)
            gage_plot_url = define_gage_data(gage_id)[
                st.session_state["gage_plot_type"]
            ]
            gage_plot_status, gage_plot_img = get_stac_img(gage_plot_url)
            # display the img
            if gage_plot_status:
                col3.markdown("## Analytics")
                col3.write(f"""Collection of USGS streamflow gages in the {st.session_state["pilot"]}
                        Watershed containing more than 15 years of annual maxima observations.
                        Note that the LP-III computations do not include regional skew. This is
                        a provisional collection, pending added datasets curated by engineers
                        developing the hydrologic model.
                        """)
                col3.image(gage_plot_img, use_container_width=True)
            else:
                col3.error("Unable to retrieve the gage plot.")
                col3.write(f"URL: {gage_plot_img}")
            # display the metadata
            if gage_meta_status:
                col4.markdown("## Metadata")
                col4.write(gage_meta["properties"])
            else:
                col4.error("Unable to retrieve the gage metadata.")
                col4.write(f"URL: {gage_meta_url}")
        # Gage Dropdown Selection
        elif st.session_state["sel_gage_id"] is not None:
            # Display the gage information if a gage is selected
            gage_id = st.session_state["sel_gage_id"]
            gage_meta_url = define_gage_data(gage_id)["Metadata"]
            gage_meta_status, gage_meta = get_stac_meta(gage_meta_url)
            gage_plot_url = define_gage_data(gage_id)[
                st.session_state["gage_plot_type"]
            ]
            gage_plot_status, gage_plot_img = get_stac_img(gage_plot_url)
            # display the metadata
            if gage_meta_status:
                col4.markdown("## Metadata")
                col4.write(gage_meta["properties"])
            else:
                col4.error("Unable to retrieve the gage metadata.")
                col4.write(f"URL: {gage_meta_url}")
            # display the img
            if gage_plot_status:
                col3.markdown("## Analytics")
                col3.write(f"""Collection of USGS streamflow gages in the {st.session_state["pilot"]}
                        Watershed containing more than 15 years of annual maxima observations.
                        Note that the LP-III computations do not include regional skew. This is
                        a provisional collection, pending added datasets curated by engineers
                        developing the hydrologic model.
                        """)
                col3.image(gage_plot_img, use_container_width=True)
            else:
                col3.error("Unable to retrieve the gage plot.")
                col3.write(f"URL: {gage_plot_img}")
        else:
            col2.write(
                "Please select a gage from the map or sidebar dropdown to view analytics."
            )
    elif selected_layer == "Storms":
        col2.write("Download the map layer")
        col2.link_button("Storms", st.pilot_layers["Storms"])
        # Storm Map Selection
        if st.sel_map_obj is not None and "Storms" in st.sel_map_obj["layer"].values:
            storm_rank = int(st.sel_map_obj["rank"].values[0])
            storm_meta_url = define_storm_data(storm_rank)["Metadata"]
            storm_meta_status, storm_meta = get_stac_meta(storm_meta_url)
            # display the metadata
            if storm_meta_status:
                storm_plot_url = storm_meta["assets"]["thumbnail"]["href"]
                storm_plot_status, storm_plot_img = get_stac_img(storm_plot_url)
                col4.markdown("## Metadata")
                col4.write(storm_meta["properties"])
            else:
                col4.error("Error: Unable to retrieve the metadata.")
                col4.write(f"URL: {storm_meta_url}")
            # display the img
            if storm_meta_status and storm_plot_status:
                col3.markdown("## Analytics")
                col3.write(f"""Collection of the top storms developed in the {st.session_state["pilot"]}
                            Watershed for a 72-hour storm period.
                            """)
                col3.image(storm_plot_img, use_container_width=True)
            else:
                col3.error("Error: Unable to retrieve the plot.")
                col3.write(f"URL: {storm_plot_img}")
        # Storm Dropdown Selection
        elif st.session_state["sel_storm_rank"] is not None:
            # Display the storm information if a storm is selected
            storm_rank = int(st.session_state["sel_storm_rank"])
            storm_meta_url = define_storm_data(storm_rank)["Metadata"]
            storm_meta_status, storm_meta = get_stac_meta(storm_meta_url)
            # display the metadata
            if storm_meta_status:
                storm_plot_url = storm_meta["assets"]["thumbnail"]["href"]
                storm_plot_status, storm_plot_img = get_stac_img(storm_plot_url)
                col4.markdown("## Metadata")
                col4.write(storm_meta["properties"])
            else:
                col4.error("Error: Unable to retrieve the metadata.")
                col4.write(f"URL: {storm_meta_url}")
            # display the img
            if storm_meta_status and storm_plot_status:
                col3.markdown("## Analytics")
                col3.write(f"""Collection of the top storms developed in the {st.session_state["pilot"]}
                            Watershed for a 72-hour storm period.
                            """)
                col3.image(storm_plot_img, use_container_width=True)
            else:
                col3.error("Error: Unable to retrieve the plot.")
                col3.write(f"URL: {storm_plot_img}")
        else:
            col2.write(
                "Please select a storm from the map or sidebar dropdown to view analytics."
            )
    elif selected_layer == "Dams":
        col2.write("Download the map layer")
        col2.link_button("Dams", st.pilot_layers["Dams"])
        # Dam Map Selection
        if st.sel_map_obj is not None and "Dams" in st.sel_map_obj["layer"].values:
            dam_id = st.sel_map_obj["id"].values[0]
            dam_meta_url = define_dam_data(dam_id)["Metadata"]
            dam_meta_status, dam_meta = get_stac_meta(dam_meta_url)
            # display the metadata
            if dam_meta_status:
                col4.markdown("## Metadata")
                # update the href in each asset to point to the full url for downloading
                for key, asset in dam_meta["assets"].items():
                    asset["href"] = f"{st.pilot_base_url}/dams/non-usace/{dam_id}/{key}"
                col4.write(dam_meta["assets"])
            else:
                col4.error("Error: Unable to retrieve the metadata.")
                col4.write(f"URL: {dam_meta_url}")
        # Dam Dropdown Selection
        elif st.session_state["sel_dam_id"] is not None:
            # Display the dam information if a dam is selected
            dam_id = st.session_state["sel_dam_id"]
            dam_meta_url = define_dam_data(dam_id)["Metadata"]
            dam_meta_status, dam_meta = get_stac_meta(dam_meta_url)
            # display the metadata
            if dam_meta_status:
                col4.markdown("## Metadata")
                # update the href in each asset to point to the full url for downloading
                for key, asset in dam_meta["assets"].items():
                    asset["href"] = f"{st.pilot_base_url}/dams/non-usace/{dam_id}/{key}"
                col4.write(dam_meta["assets"])
            else:
                col4.error("Error: Unable to retrieve the metadata.")
                col4.write(f"URL: {dam_meta_url}")
        else:
            col2.write(
                "Please select a dam from the map or sidebar dropdown to view analytics."
            )
    elif selected_layer == "COGs":
        # COG cmap selection in the sidebar
        cmap_names = [
            "rainbow",
            "viridis",
            "plasma",
            "cividis",
            "magma",
            "inferno",
            "coolwarm",
            "spectral",
            "ocean",
            "jet",
        ]
        st.session_state["sel_cmap"] = col2.selectbox(
            "Select a COG Colormap",
            cmap_names,
            index=0,
        )
        if (
            st.session_state["cog_stats"] is not None
            and "b1" in st.session_state["cog_stats"]
        ):
            cog_stats = st.session_state["cog_stats"]["b1"]
            cog_hist = cog_stats["histogram"]
            # plot a histogram of the COG
            hist_df = pd.DataFrame(cog_hist).T
            hist_df.columns = ["Count", "Value"]
            st.session_state["cog_hist_nbins"] = col2.slider(
                "Select number of bins for histogram",
                min_value=5,
                max_value=100,
                value=20,
            )
            hist_fig = plot_hist(
                hist_df,
                x_col="Value",
                y_col="Count",
                nbins=st.session_state["cog_hist_nbins"],
            )
            col3.markdown("## Analytics")
            col3.plotly_chart(hist_fig, use_container_width=True)
            col4.markdown("## Metadata")
            col4.write(cog_stats)
        else:
            col2.write(st.session_state["cog_stats"])
    elif selected_layer == "Reference Lines":
        col2.write("Download the map layer")
        col2.link_button("Reference Lines", st.pilot_layers["Reference Lines"])
        if (
            st.sel_map_obj is not None
            and "Reference Lines" in st.sel_map_obj["layer"].values
        ):
            ref_line_id = st.sel_map_obj["id"].values[0]
            col2.write(f"Selected Reference Line: {ref_line_id}")
            ref_line_ts = get_ref_line_ts(ref_line_id)
            plot_ts(ref_line_ts, "water_surface", col3)
            plot_ts(ref_line_ts, "flow", col4)
        elif st.session_state["sel_ref_line_id"] is not None:
            # Display the reference line information if a reference line is selected
            ref_line_id = st.session_state["sel_ref_line_id"]
            col2.write(f"Selected Reference Line: {ref_line_id}")
            ref_line_ts = get_ref_line_ts(ref_line_id)
            plot_ts(ref_line_ts, "water_surface", col3)
            plot_ts(ref_line_ts, "flow", col4)
        else:
            col2.write(
                "Please select a reference line from the map or sidebar dropdown to view analytics."
            )
    elif selected_layer == "Reference Points":
        col2.write("Download the map layer")
        col2.link_button("Reference Points", st.pilot_layers["Reference Points"])
        if (
            st.sel_map_obj is not None
            and "Reference Points" in st.sel_map_obj["layer"].values
        ):
            ref_point_id = st.sel_map_obj["id"].values[0]
            col2.write(f"Selected Reference Point: {ref_point_id}")
            ref_pt_ts = get_ref_pt_ts(ref_point_id)
            plot_ts(ref_pt_ts, "water_surface", col3)
            plot_ts(ref_pt_ts, "velocity", col4)
        elif st.session_state["sel_ref_point_id"] is not None:
            # Display the reference point information if a reference point is selected
            ref_point_id = st.session_state["sel_ref_point_id"]
            col2.write(f"Selected Reference Point: {ref_point_id}")
            ref_pt_ts = get_ref_pt_ts(ref_point_id)
            plot_ts(ref_pt_ts, "water_surface", col3)
            plot_ts(ref_pt_ts, "velocity", col4)
        else:
            col2.write(
                "Please select a reference point from the map or sidebar dropdown to view analytics."
            )

    # Session state
    with st.expander("Session State"):
        st.write(st.session_state)

    # Footer
    render_footer()


if __name__ == "__main__":
    single_event()
