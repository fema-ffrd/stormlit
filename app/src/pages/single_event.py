# module imports
from ..components.layout import render_footer
from ..configs.settings import LOG_LEVEL
from ..utils.session import init_session_state
from ..utils.stac_data import (
    init_pilot,
    define_gage_data,
    define_storm_data,
    define_dam_data,
    get_stac_img,
    get_stac_meta,
    get_ref_line_ts,
    get_ref_pt_ts,
)
from ..utils.functions import (
    create_st_button,
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

# Suppress warnings
warnings.filterwarnings("ignore")

currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
assetsDir = os.path.abspath(os.path.join(srcDir, "assets"))  # go up one level to src
load_dotenv()


def single_event():
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

    st.sidebar.markdown("## Initalize the Pilot Study")
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

    st.sidebar.markdown("## Select Layers from Dropdown")
    st.sidebar.markdown("You know what you want but don't know where it is.")

    basin_id_list = sorted(st.basins["NAME"].unique().tolist())
    st.session_state["sel_basin_id"] = st.sidebar.selectbox(
        "Select a Basin by Name",
        basin_id_list,
        index=None,
    )
    gage_id_list = sorted(st.gages["site_no"].unique().tolist())
    st.session_state["sel_gage_id"] = st.sidebar.selectbox(
        "Select a Gage by ID",
        gage_id_list,
        index=None,
    )
    storm_rank_list = sorted(st.storms["rank"].unique().tolist())
    st.session_state["sel_storm_rank"] = st.sidebar.selectbox(
        "Select a Storm by Rank",
        storm_rank_list,
        index=None,
    )
    dam_id_list = sorted(st.dams["id"].unique().tolist())
    st.session_state["sel_dam_id"] = st.sidebar.selectbox(
        "Select a Dam by ID",
        dam_id_list,
        index=None,
    )
    cog_id_list = sorted(list(st.cog_layers.keys()))
    st.session_state["sel_cog_layer"] = st.sidebar.selectbox(
        "Select a COG by Name",
        cog_id_list,
        index=None,
    )
    ref_line_id_list = sorted(st.ref_lines["id"].unique().tolist())
    st.session_state["sel_ref_line_id"] = st.sidebar.selectbox(
        "Select a Reference Line by ID",
        ref_line_id_list,
        index=None,
    )
    ref_point_id_list = sorted(st.ref_points["id"].unique().tolist())
    st.session_state["sel_ref_point_id"] = st.sidebar.selectbox(
        "Select a Reference Point by ID",
        ref_point_id_list,
        index=None,
    )
    st.sidebar.markdown("---")

    # Map layers
    map_layer_dict = {
        "Basins": st.session_state["sel_basin_id"],
        "Gages": st.session_state["sel_gage_id"],
        "Storms": st.session_state["sel_storm_rank"],
        "Dams": st.session_state["sel_dam_id"],
    }
    # filter out None values
    sel_layers = {k: v for k, v in map_layer_dict.items() if v is not None}

    col3, col4 = st.columns(2)
    with col3:
        # Select which layer to zoom to in the map
        st.session_state["zoom_to_layer"] = st.selectbox(
            "Zoom to a Selected Layer",
            list(sel_layers.keys()),
            index=None,
        )
        # Get the map position based on the selection
        if st.session_state["zoom_to_layer"] is not None:
            c_lat, c_lon, zoom = get_map_pos(
                st.session_state["zoom_to_layer"],
                sel_layers[st.session_state["zoom_to_layer"]],
            )
        # Default map position
        else:
            c_lat, c_lon, zoom = get_map_pos(
                "Study Area",
                None,
            )

    col5, col6 = st.columns(2)

    with col5:
        st.markdown("## Select Layers from Map")
        st.markdown("You know where to look but not what to look for.")
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

    # Display the selected object information from the map
    if st.map_output is not None:
        if st.map_output["last_object_clicked_tooltip"] is not None:
            st.sel_map_obj = get_map_sel(st.map_output)
            st.subheader("Selected Map Information")

    with col6:
        st.markdown("## View Selections")
        st.markdown(
            "Collapse each section to view metadata and analytics based on your selections."
        )
        with st.expander("Basins"):
            st.write("Download the map layer")
            create_st_button(
                "Basins", st.pilot_layers["Basins"], background_color="#1e90ff"
            )
            # Basin Map Selection
            if st.sel_map_obj is not None:
                if "Basins" in st.sel_map_obj["layer"].values:
                    basin_id = st.sel_map_obj["HUC8"].values[0]
                    basin_gdf = st.basins[st.basins["HUC8"] == basin_id]
                    st.dataframe(basin_gdf.drop(columns=["geometry"]))
            # Basin Dropdown Selection
            elif st.session_state["sel_basin_id"] is not None:
                basin_id = st.session_state["sel_basin_id"]
                basin_gdf = st.basins[st.basins["NAME"] == basin_id]
                st.dataframe(basin_gdf.drop(columns=["geometry"]))
        with st.expander("Gages"):
            st.write("Download the map layer")
            create_st_button(
                "Gages", st.pilot_layers["Gages"], background_color="#32cd32"
            )
            st.session_state["gage_plot_type"] = st.selectbox(
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
                    st.markdown("## Analytics")
                    st.write(f"""Collection of USGS streamflow gages in the {st.session_state["pilot"]}
                            Watershed containing more than 15 years of annual maxima observations.
                            Note that the LP-III computations do not include regional skew. This is
                            a provisional collection, pending added datasets curated by engineers
                            developing the hydrologic model.
                            """)
                    st.image(gage_plot_img, use_container_width=True)
                else:
                    st.error("Unable to retrieve the gage plot.")
                    st.write(f"URL: {gage_plot_img}")
                # display the metadata
                if gage_meta_status:
                    st.markdown("## Metadata")
                    st.write(gage_meta["properties"])
                else:
                    st.error("Unable to retrieve the gage metadata.")
                    st.write(f"URL: {gage_meta_url}")
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
                    st.markdown("## Metadata")
                    st.write(gage_meta["properties"])
                else:
                    st.error("Unable to retrieve the gage metadata.")
                    st.write(f"URL: {gage_meta_url}")
                # display the img
                if gage_plot_status:
                    st.markdown("## Analytics")
                    st.write(f"""Collection of USGS streamflow gages in the {st.session_state["pilot"]}
                            Watershed containing more than 15 years of annual maxima observations.
                            Note that the LP-III computations do not include regional skew. This is
                            a provisional collection, pending added datasets curated by engineers
                            developing the hydrologic model.
                            """)
                    st.image(gage_plot_img, use_container_width=True)
                else:
                    st.error("Unable to retrieve the gage plot.")
                    st.write(f"URL: {gage_plot_img}")
            else:
                st.write(
                    "Please select a gage from the map or sidebar dropdown to view analytics."
                )
        with st.expander("Storms"):
            st.write("Download the map layer")
            create_st_button(
                "Storms", st.pilot_layers["Storms"], background_color="#ed9121"
            )
            # Storm Map Selection
            if (
                st.sel_map_obj is not None
                and "Storms" in st.sel_map_obj["layer"].values
            ):
                storm_rank = int(st.sel_map_obj["rank"].values[0])
                storm_meta_url = define_storm_data(storm_rank)["Metadata"]
                storm_meta_status, storm_meta = get_stac_meta(storm_meta_url)
                # display the metadata
                if storm_meta_status:
                    storm_plot_url = storm_meta["assets"]["thumbnail"]["href"]
                    storm_plot_status, storm_plot_img = get_stac_img(storm_plot_url)
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
            else:
                st.write(
                    "Please select a storm from the map or sidebar dropdown to view analytics."
                )
        with st.expander("Dams"):
            st.write("Download the map layer")
            create_st_button(
                "Dams", st.pilot_layers["Dams"], background_color="#e32636"
            )
            # Dam Map Selection
            if st.sel_map_obj is not None and "Dams" in st.sel_map_obj["layer"].values:
                dam_id = st.sel_map_obj["id"].values[0]
                dam_meta_url = define_dam_data(dam_id)["Metadata"]
                dam_meta_status, dam_meta = get_stac_meta(dam_meta_url)
                # display the metadata
                if dam_meta_status:
                    # update the href in each asset to point to the full url for downloading
                    for key, asset in dam_meta["assets"].items():
                        asset["href"] = (
                            f"{st.pilot_base_url}/dams/non-usace/{dam_id}/{key}"
                        )
                    st.write(dam_meta["assets"])
                else:
                    st.error("Error: Unable to retrieve the metadata.")
                    st.write(f"URL: {dam_meta_url}")
            # Dam Dropdown Selection
            elif st.session_state["sel_dam_id"] is not None:
                # Display the dam information if a dam is selected
                dam_id = st.session_state["sel_dam_id"]
                dam_meta_url = define_dam_data(dam_id)["Metadata"]
                dam_meta_status, dam_meta = get_stac_meta(dam_meta_url)
                # display the metadata
                if dam_meta_status:
                    # update the href in each asset to point to the full url for downloading
                    for key, asset in dam_meta["assets"].items():
                        asset["href"] = (
                            f"{st.pilot_base_url}/dams/non-usace/{dam_id}/{key}"
                        )
                    st.write(dam_meta["assets"])
                else:
                    st.error("Error: Unable to retrieve the metadata.")
                    st.write(f"URL: {dam_meta_url}")
            else:
                st.write(
                    "Please select a dam from the map or sidebar dropdown to view analytics."
                )
        with st.expander("COGs"):
            st.markdown("## Cloud Optimized Geotiffs")
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
            st.session_state["sel_cmap"] = st.selectbox(
                "Select a COG Colormap",
                cmap_names,
                index=0,
            )
            if st.session_state["sel_cog_layer"] is not None:
                cog_stats = st.session_state["cog_stats"]["b1"]
                cog_hist = cog_stats["histogram"]
                # plot a histogram of the COG
                hist_df = pd.DataFrame(cog_hist).T
                hist_df.columns = ["Count", "Value"]
                st.session_state["cog_hist_nbins"] = st.slider(
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
                st.plotly_chart(hist_fig, use_container_width=True)
                st.write(cog_stats)
            else:
                st.write(
                    "Please select a COG from the sidebar dropdown to view analytics."
                )
        with st.expander("Reference Lines"):
            st.write("Download the map layer")
            create_st_button(
                "Reference Lines",
                st.pilot_layers["Reference Lines"],
                background_color="#1e90ff",
            )
            if (
                st.sel_map_obj is not None
                and "Reference Lines" in st.sel_map_obj["layer"].values
            ):
                ref_line_id = st.sel_map_obj["id"].values[0]
                st.write(f"Selected Reference Line: {ref_line_id}")
                ref_line_ts = get_ref_line_ts(ref_line_id)
                plot_ts(ref_line_ts, "water_surface")
                plot_ts(ref_line_ts, "flow")
            elif st.session_state["sel_ref_line_id"] is not None:
                # Display the reference line information if a reference line is selected
                ref_line_id = st.session_state["sel_ref_line_id"]
                st.write(f"Selected Reference Line: {ref_line_id}")
                ref_line_ts = get_ref_line_ts(ref_line_id)
                plot_ts(ref_line_ts, "water_surface")
                plot_ts(ref_line_ts, "flow")
            else:
                st.write(
                    "Please select a reference line from the map or sidebar dropdown to view analytics."
                )

        with st.expander("Reference Points"):
            st.write("Download the map layer")
            create_st_button(
                "Reference Points",
                st.pilot_layers["Reference Points"],
                background_color="#1e90ff",
            )
            if (
                st.sel_map_obj is not None
                and "Reference Points" in st.sel_map_obj["layer"].values
            ):
                ref_point_id = st.sel_map_obj["id"].values[0]
                st.write(f"Selected Reference Point: {ref_point_id}")
                ref_pt_ts = get_ref_pt_ts(ref_point_id)
                plot_ts(ref_pt_ts, "water_surface")
                plot_ts(ref_pt_ts, "velocity")
            elif st.session_state["sel_ref_point_id"] is not None:
                # Display the reference point information if a reference point is selected
                ref_point_id = st.session_state["sel_ref_point_id"]
                st.write(f"Selected Reference Point: {ref_point_id}")
                ref_pt_ts = get_ref_pt_ts(ref_point_id)
                plot_ts(ref_pt_ts, "water_surface")
                plot_ts(ref_pt_ts, "velocity")
            else:
                st.write(
                    "Please select a reference point from the map or sidebar dropdown to view analytics."
                )

    # Session state
    with st.expander("Session State"):
        st.write(st.session_state)

    # Footer
    render_footer()
