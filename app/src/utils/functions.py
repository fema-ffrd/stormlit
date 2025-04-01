import re
import folium
import uuid
import streamlit as st
import geopandas as gpd
import subprocess
import pandas as pd
import socket
import random
from plotly import express as px


def create_st_button(
    link_text: str,
    link_url: str,
    background_color="rgb(255, 255, 255)",
    hover_color="#f2f3f4",
    st_col=None,
):
    """
    Create a Streamlit button with a hover effect

    Parameters
    ----------
    link_text: str
        The text to display on the button
    link_url: str
        The URL to open when the button is clicked
    hover_color: str
        The color to change to when the button is hovered over
    st_col: streamlit.delta_generator.DeltaGenerator
        The streamlit column to display the button in
    """

    button_uuid = str(uuid.uuid4()).replace("-", "")
    button_id = re.sub("\d+", "", button_uuid)

    button_css = f"""
        <style>
            #{button_id} {{
                background-color: {background_color};
                color: rgb(38, 39, 48);
                padding: 0.25em 0.38em;
                position: relative;
                text-decoration: none;
                border-radius: 4px;
                border-width: 2px;
                border-style: solid;
                border-color: rgb(230, 234, 241);
                border-image: initial;

            }}
            #{button_id}:hover {{
                border-color: {hover_color};
                color: {hover_color};
            }}
            #{button_id}:active {{
                box-shadow: none;
                background-color: {hover_color};
                color: white;
                }}
        </style> """

    html_str = f'<a href="{link_url}" target="_blank" id="{button_id}";>{link_text}</a><br></br>'

    if st_col is None:
        st.markdown(button_css + html_str, unsafe_allow_html=True)
    else:
        st_col.markdown(button_css + html_str, unsafe_allow_html=True)


def add_polygons_fg(
    gdf: gpd.GeoDataFrame,
    layer_name: str,
    tooltip_fields: list,
    style_function: callable,
):
    """
    Add polygons to a folium map as a feature group

    Parameters
    ----------
    gdf: gpd.GeoDataFrame
        A GeoDataFrame with polygon geometries
    layer_name: str
        The name of the layer to add to the map
    tooltip_fields: list
        A list of fields to display in the tooltip
    style_function: callable
        A function to style the polygons

    Returns
    -------
    folium.FeatureGroup
        A folium feature group containing the polygons
    """

    fg_polygons = folium.FeatureGroup(name=layer_name)
    fg_polygons.add_child(
        folium.GeoJson(
            gdf,
            name=layer_name,
            zoom_on_click=True,
            style_function=style_function,
            tooltip=folium.GeoJsonTooltip(fields=tooltip_fields),
        )
    )
    return fg_polygons


def add_markers_fg(
    gdf: gpd.GeoDataFrame,
    layer_name: str,
    tooltip_fields: list,
    style_function: callable,
):
    """
    Add markers to a folium map as a feature group

    Parameters
    ----------
    gdf: gpd.GeoDataFrame
        A GeoDataFrame with point geometries
    layer_name: str
        The name of the layer to add to the map
    tooltip_fields: list
        A list of fields to display in the tooltip
    style_function: callable
        A function to style the markers

    Returns
    -------
    folium.FeatureGroup
        A folium feature group containing the markers
    """
    fg_markers = folium.FeatureGroup(name=layer_name)
    fg_markers.add_child(
        folium.GeoJson(
            gdf,
            marker=folium.Marker(icon=folium.Icon()),
            name=layer_name,
            zoom_on_click=True,
            style_function=style_function,
            tooltip=folium.GeoJsonTooltip(fields=tooltip_fields),
        )
    )
    return fg_markers


def add_circles_fg(
    gdf: gpd.GeoDataFrame,
    layer_name: str,
    tooltip_fields: list,
    style_function: callable,
):
    """
    Add circles to a folium map as a feature group

    Parameters
    ----------
    gdf: gpd.GeoDataFrame
        A GeoDataFrame with point geometries
    layer_name: str
        The name of the layer to add to the map
    tooltip_fields: list
        A list of fields to display in the tooltip
    style_function: callable
        A function to style the circles

    Returns
    -------
    folium.FeatureGroup
        A folium feature group containing the circles
    """
    fg_circles = folium.FeatureGroup(name=layer_name)
    fg_circles.add_child(
        folium.GeoJson(
            gdf,
            marker=folium.Circle(
                radius=1500,
                fill_color="blue",
                fill_opacity=0.5,
                color="black",
                weight=1,
            ),
            style_function=style_function,
            name=layer_name,
            zoom_on_click=True,
            tooltip=folium.GeoJsonTooltip(fields=tooltip_fields),
        )
    )
    return fg_circles


def style_basins(feature):
    return {"fillColor": "#1e90ff"}


def style_dams(feature):
    return {"fillColor": "#e32636"}


def style_gages(feature):
    return {"fillColor": "#32cd32"}


def style_storms(feature):
    return {"fillColor": "#ed9121"}


def style_ref_lines(feature):
    return {"fillColor": "#1e90ff"}


def style_ref_points(feature):
    return {"fillColor": "#1e90ff"}


@st.cache_data
def prep_fmap(
    sel_layers: list,
    basemap: str = "OpenStreetMap",
    basin_name: str = None,
    storm_rank: int = None,
):
    """
    Prep a folium map object given a geojson with a specificed basemap

    Parameters
    ----------
    sel_layers: dict
        A list of selected map layers to plot
    basemap: str
        Basemap to use for the map.
        Options are "OpenStreetMap", "ESRI Satellite", and "Google Satellite"
    basin_name: str
        The basin name to plot additional data for
    storm_rank: int
        The rank of the storm to plot

    Returns
    -------
    folium.Map
        Folium map object
    """
    df_dict = {}
    for layer in sel_layers:
        if layer == "Basins" and st.basins is not None:
            df_dict["Basins"] = st.basins
        elif layer == "Dams" and st.dams is not None:
            df_dict["Dams"] = st.dams
        elif layer == "Gages" and st.gages is not None:
            df_dict["Gages"] = st.gages
        elif layer == "Storms" and st.storms is not None:
            df_dict["Storms"] = st.storms
        else:
            pass

    if basin_name is not None:
        # Get the centroid from the selected basin
        c_df = df_dict["Basins"]
        c_lat, c_lon = (
            c_df[c_df["NAME"] == basin_name]["lat"].mean(),
            c_df[c_df["NAME"] == basin_name]["lon"].mean(),
        )
        c_zoom = 10
    elif storm_rank is not None:
        # Get the centroid from the selected storm
        c_df = df_dict["Storms"]
        c_lat, c_lon = (
            c_df[c_df["rank"] == storm_rank]["lat"].mean(),
            c_df[c_df["rank"] == storm_rank]["lon"].mean(),
        )
        c_zoom = 12
    else:
        # Get the centroid of the pilot study area
        c_df = df_dict["Basins"]
        c_lat, c_lon = c_df["lat"].mean(), c_df["lon"].mean()
        c_zoom = 8

    # Create a folium map centered at the mean latitude and longitude
    m = folium.Map(location=[c_lat, c_lon], zoom_start=c_zoom)
    # Specify the basemap
    if basemap == "ESRI Satellite":
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri",
            name="Esri Satellite",
            overlay=False,
            control=True,
        ).add_to(m)
    elif basemap == "Google Satellite":
        folium.TileLayer(
            tiles="http://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
            attr="Google",
            name="Google Satellite",
            overlay=False,
            control=True,
        ).add_to(m)
    else:
        folium.TileLayer("openstreetmap").add_to(m)

    idx = 0

    for key, df in df_dict.items():
        df["layer"] = key
        # Add the GeoDataFrames geometry to the map
        if key == "Basins":
            fg_basins = add_polygons_fg(
                df, sel_layers[idx], ["layer", "HUC8", "NAME"], style_basins
            )
            fg_basins.add_to(m)
        elif key == "Dams":
            fg_dams = add_circles_fg(df, sel_layers[idx], ["layer", "id"], style_dams)
            fg_dams.add_to(m)
        elif key == "Gages":
            fg_gages = add_circles_fg(
                df, sel_layers[idx], ["layer", "site_no"], style_gages
            )
            fg_gages.add_to(m)
        elif key == "Storms":
            fg_storms = add_circles_fg(
                df, sel_layers[idx], ["layer", "rank", "storm_type"], style_storms
            )
            fg_storms.add_to(m)
        else:
            pass
        idx += 1

    if basin_name is not None:
        # plot the reference lines and points
        if basin_name in st.ref_lines["NAME"].unique():
            ref_lines = st.ref_lines.loc[st.ref_lines["NAME"] == basin_name]
            ref_lines["layer"] = "Reference Lines"
            fg_ref_lines = add_polygons_fg(
                ref_lines,
                "Reference Lines",
                ["layer", "id", "line_type"],
                style_ref_lines,
            )
            fg_ref_lines.add_to(m)
        if basin_name in st.ref_points["NAME"].unique():
            ref_points = st.ref_points.loc[st.ref_points["NAME"] == basin_name]
            ref_points["layer"] = "Reference Points"
            fg_ref_points = add_markers_fg(
                ref_points,
                "Reference Points",
                ["layer", "id", "point_type"],
                style_ref_points,
            )
            fg_ref_points.add_to(m)
    # Add the layer control to the map
    folium.LayerControl().add_to(m)
    return m


def get_map_sel(map_output: str):
    """
    Return the selection from the map as a filtered GeoDataFrame

    Parameters
    ----------
    map_output: str
        The map output from the folium map

    Returns
    -------
    pd.DataFrame
        A filtered GeoDataFrame based on the map selection
    """
    tooltip_text = map_output["last_object_clicked_tooltip"]
    # Split the tooltip multi line string into objects
    items = tooltip_text.split("\n")
    # Remove any empty strings and spaces
    items = [item.replace(" ", "") for item in items if len(item.replace(" ", "")) > 0]
    # layer_col = items[0]  # layer column
    layer_val = items[1]  # layer value
    # id_col = items[2]  # id column
    id_val = items[3]  # id value
    df = None

    # Filter the GeoDataFrame based on the map selection
    if layer_val == "Basins" and st.basins is not None:
        df = st.basins
        df = df[df["HUC8"] == id_val]
    elif layer_val == "Dams" and st.dams is not None:
        df = st.dams
        df = df[df["id"] == id_val]
    elif layer_val == "Gages" and st.gages is not None:
        df = st.gages
        df = df[df["site_no"] == id_val]
    elif layer_val == "Storms" and st.storms is not None:
        df = st.storms
        df = df[df["rank"] == int(id_val)]
    elif layer_val == "ReferenceLines" and st.ref_lines is not None:
        df = st.ref_lines
        df = df[df["id"] == id_val]
    elif layer_val == "ReferencePoints" and st.ref_points is not None:
        df = st.ref_points
        df = df[df["id"] == id_val]
    else:
        st.write(f"Pasing on layer {layer_val}")
        pass
    return df


def is_port_available(port: int):
    """
    Check if a port is available.

    Parameters
    ----------
    port : int
        The port number to check.

    Returns
    -------
    bool
        True if the port is available, False otherwise.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def init_cog(path, port=None):
    """
    Initializes a local server to visualize a COG file using rasterio's rio viz command.

    Parameters
    ----------
    path : str
        The path to the cog file.
    port : int
        The port to run the server on. Default is 8080.

    """
    # Find an available port if none is provided
    if port is None:
        while True:
            port = random.randint(
                1024, 65535
            )  # Use a port in the dynamic/private range
            if is_port_available(port):
                break

    # Ensure the specified port is available
    if not is_port_available(port):
        raise ValueError(
            f"Port {port} is already in use. Please specify a different port."
        )

    # Start the rio viz server in the background
    subprocess.run(
        ["rio", "viz", path, "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def kill_cog():
    """
    Kills the COG server process if it is running.
    """
    try:
        subprocess.run(["pkill", "-f", "rio viz"], check=True)
        st.write("Server terminated successfully.")
    except subprocess.CalledProcessError:
        st.write("No running server found to terminate.")


def plot_ts(df: pd.DataFrame, var: str):
    """
    Function for plotting time series data.
    Columns in the DataFrame should be:
    - 'id': str
    - 'time': datetime
    - 'velocity': float
    - 'water_surface': float
    - 'flow': float

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame containing the time series data.
    var : str
        The variable to plot.
    """
    # Check if the DataFrame is empty
    if df.empty:
        st.warning("No data available for the selected variable.")
        return

    # Check if the required columns are present in the DataFrame
    required_columns = ["id", "time", var]
    if not all(col in df.columns for col in required_columns):
        st.error(f"DataFrame must contain the following columns: {required_columns}")
        return

    # Create a line plot using Streamlit
    fig = px.line(df, x="time", y=var, title=f"Time Series Plot of {var}")
    st.plotly_chart(fig)
