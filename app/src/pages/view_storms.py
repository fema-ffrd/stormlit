# standard imports
import os
import sys
import folium
import geopandas as gpd
import streamlit as st
from shapely import wkt
from shapely.geometry import Point
from streamlit_folium import st_folium
from dotenv import load_dotenv

# global variables
STORMS_DATA = "s3://kanawha-pilot/stac/Kanawha-0505/data-summary/storms.pq"
currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
sys.path.append(srcDir)
load_dotenv()

# custom imports
from utils.stac_data import init_storm_data
from utils.session import init_session_state
from components.layout import render_footer
from configs.settings import LOG_LEVEL


def swap_coordinates(point_str):
    """Fix for error in stac items, need to fix in catalog and return wkt.loads(point_str)"""
    point = wkt.loads(point_str)
    return Point(point.x, point.y)


def view_storms():
    if "session_id" not in st.session_state:
        init_session_state()

    st.stac_url = os.getenv("STAC_API_URL")

    st.session_state.log_level = LOG_LEVEL

    if st.session_state["init_storm_data"] is False:
        st.write("Initializing datasets...")
        init_storm_data(STORMS_DATA)
        st.session_state["init_storm_data"] = True
        st.balloons()
        st.success("Complete! Storm data is now ready for exploration.")

    st.markdown("## Storm Viewer")

    df = st.storms.rename(
        columns={
            "block_group": "Block",
            "historic_storm_date": "Date",
            "historic_storm_season": "Season",
            "historic_storm_max_precip_inches": "Max Precip (in)",
            "realization": "Realization",
            "date": "Date",
        }
    )

    # create a sidebar for all of the input filters
    st.sidebar.title("Input Search Filters")

    # with search_col1:
    sieve1 = df.copy()
    st.session_state["realization"] = st.sidebar.multiselect(
        "Select by Realization",
        sieve1["Realization"].unique(),
        default=list(sieve1["Realization"].unique())[0],
    )
    sieve1 = sieve1[sieve1["Realization"].isin(st.session_state["realization"])]
    st.session_state["block"] = st.sidebar.slider(
        "Select by Block Range",
        min_value=sieve1["Block"].min(),
        max_value=sieve1["Block"].max(),
        value=(122, 255),
    )
    sieve1 = sieve1[
        (sieve1["Block"] >= st.session_state["block"][0])
        & (sieve1["Block"] <= st.session_state["block"][1])
    ]

    st.session_state["search_id"] = st.sidebar.multiselect(
        "Search by ID", sieve1["ID"].unique()
    )
    if len(st.session_state["search_id"]) > 0:
        st.write("filtering by search_id")
        sieve1 = sieve1[sieve1["ID"].isin(st.session_state["search_id"])]

    # with search_col2:
    if sieve1["Max Precip (in)"].min() != sieve1["Max Precip (in)"].max():
        st.session_state["max_precip"] = st.sidebar.slider(
            "Search by Max Precipitation (inches)",
            min_value=sieve1["Max Precip (in)"].min(),
            max_value=sieve1["Max Precip (in)"].max(),
            value=sieve1["Max Precip (in)"].mean(),
            step=0.1,
        )
        sieve1 = sieve1[sieve1["Max Precip (in)"] >= st.session_state["max_precip"]]

    st.session_state["storm_season"] = st.sidebar.multiselect(
        "Search for Seasonal Storms",
        ["All", "spring", "summer", "fall", "winter"],
        default=["All"],
    )
    if "All" not in st.session_state["storm_season"]:
        sieve1 = sieve1[sieve1["Season"].isin(st.session_state["storm_season"])]

    st.session_state["storm_date"] = st.sidebar.multiselect(
        "Search by Storm Date", ["All", *sieve1["Date"].unique()], default=["All"]
    )
    if "All" not in st.session_state["storm_date"]:
        sieve1 = sieve1[sieve1["Date"].isin(st.session_state["storm_date"])]

    st.write("Filtered Dataset")
    st.dataframe(sieve1)

    if len(sieve1) > 0:
        # Create a gdf for the SST storm center points
        sst_gdf = sieve1.copy()
        sst_gdf["geometry"] = sst_gdf["SST_storm_center"].apply(swap_coordinates)
        sst_gdf = gpd.GeoDataFrame(sst_gdf, geometry="geometry")

        # Create a gdf for the historic storm center points
        historic_gdf = sieve1.copy()
        historic_gdf["geometry"] = historic_gdf["historic_storm_center"].apply(
            swap_coordinates
        )
        historic_gdf = gpd.GeoDataFrame(historic_gdf, geometry="geometry")

        # initialize the maps
        m1 = folium.Map(location=[37.75153, -80.94911], zoom_start=6)
        folium.GeoJson(f"{st.stac_url}/collections/Kanawha-R01/items/E005125").add_to(
            m1
        )
        m2 = folium.Map(location=[37.75153, -80.94911], zoom_start=6)
        folium.GeoJson(f"{st.stac_url}/collections/Kanawha-R01/items/E005125").add_to(
            m2
        )

        # create a heatmap for the historic storm center points
        folium.plugins.HeatMap(
            data=historic_gdf["geometry"].apply(lambda pt: [pt.y, pt.x]).tolist()
        ).add_to(m1)
        # create a heatmap for the SST storm center points
        folium.plugins.HeatMap(
            data=sst_gdf["geometry"].apply(lambda pt: [pt.y, pt.x]).tolist()
        ).add_to(m2)

        col3, col4 = st.columns(2)
        with col3:
            st.write("Historic Storm Centers Heatmap")
            st_folium(m1, width=700, height=700, key="m1")
        with col4:
            st.write("SST Storm Centers Heatmap")
            st_folium(m2, width=700, height=700, key="m2")

    render_footer()
