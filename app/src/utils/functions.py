import os
import requests
import folium
import streamlit as st
import geopandas as gpd
import pandas as pd
from plotly import express as px
import plotly.graph_objects as go
from typing import List, Optional


def highlight_function(feature):
    return {
        "fillColor": "yellow",
        "color": "black",
        "weight": 3,
        "opacity": 0.5,
    }


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
            highlight_function=highlight_function,
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
            highlight_function=highlight_function,
            tooltip=folium.GeoJsonTooltip(fields=tooltip_fields),
        )
    )
    return fg_markers


def add_circles_fg(
    gdf: gpd.GeoDataFrame,
    layer_name: str,
    tooltip_fields: list,
    color: str,
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
    color: str
        The color of the circles

    Returns
    -------
    folium.FeatureGroup
        A folium feature group containing the circles
    """
    # Create a DivIcon marker
    div_icon = folium.DivIcon(
        html=f"""
        <div style="
            background-color: {color};
            border: 1px solid black;
            border-radius: 0;
            width: 10px;
            height: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            color: white;">
        </div>
        """
    )

    fg_circles = folium.FeatureGroup(name=layer_name)
    fg_circles.add_child(
        folium.GeoJson(
            gdf,
            name=layer_name,
            marker=folium.Marker(icon=div_icon),
            tooltip=folium.GeoJsonTooltip(fields=tooltip_fields),
            popup=folium.GeoJsonPopup(fields=tooltip_fields),
            highlight_function=highlight_function,
            zoom_on_click=True,
        )
    )

    return fg_circles


def style_basins(feature):
    return {"fillColor": "#1e90ff"}


def style_ref_lines(feature):
    return {"fillColor": "#1e90ff"}


def style_ref_points(feature):
    return {"fillColor": "#1e90ff"}


def get_map_pos(map_layer: str, layer_field: str):
    """
    Get the map position based on the selected layer and field.

    Parameters
    ----------
    map_layer: str
        The selected map layer
    layer_field: str
        The selected layer field
    Returns
    -------
    tuple
        A tuple containing the latitude, longitude, and zoom level
    """
    if map_layer == "Basins":
        # Get the centroid from the selected basin
        c_df = st.basins
        c_lat, c_lon = (
            c_df[c_df["NAME"] == layer_field]["lat"].mean(),
            c_df[c_df["NAME"] == layer_field]["lon"].mean(),
        )
        c_zoom = 10
    elif map_layer == "Gages":
        # Get the centroid from the selected gage
        c_df = st.gages
        c_lat, c_lon = (
            c_df[c_df["site_no"] == layer_field]["lat"].mean(),
            c_df[c_df["site_no"] == layer_field]["lon"].mean(),
        )
        c_zoom = 14
    elif map_layer == "Dams":
        # Get the centroid from the selected dam
        c_df = st.dams
        c_lat, c_lon = (
            c_df[c_df["id"] == layer_field]["lat"].mean(),
            c_df[c_df["id"] == layer_field]["lon"].mean(),
        )
        c_zoom = 14
    elif map_layer == "Storms":
        # Get the centroid from the selected storm
        c_df = st.storms
        c_lat, c_lon = (
            c_df[c_df["rank"] == layer_field]["lat"].mean(),
            c_df[c_df["rank"] == layer_field]["lon"].mean(),
        )
        c_zoom = 14
    else:
        # Get the centroid of the pilot study area
        c_df = st.basins
        c_lat, c_lon = c_df["lat"].mean(), c_df["lon"].mean()
        c_zoom = 8
    # print(f"Latitude: {c_lat}, Longitude: {c_lon}, Zoom: {c_zoom}, Layer: {map_layer}, Field: {layer_field}")
    return c_lat, c_lon, c_zoom


@st.cache_data
def prep_fmap(
    sel_layers: list,
    cog_layer: str = None,
    cmap_name: str = "viridis",
):
    """
    Prep a folium map object given a geojson with a specificed basemap

    Parameters
    ----------
    sel_layers: dict
        A list of selected map layers to plot
    cog_layer: str
        The name of the COG layer to add to the map
    cmap_name: str
        The colormap name to use for the COG layer

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
        elif layer == "Reference Lines" and st.ref_lines is not None:
            df_dict["Reference Lines"] = st.ref_lines
        elif layer == "Reference Points" and st.ref_points is not None:
            df_dict["Reference Points"] = st.ref_points
        else:
            pass

    c_df = st.basins
    c_lat, c_lon = c_df["lat"].mean(), c_df["lon"].mean()

    # Create a folium map centered at the mean latitude and longitude
    m = folium.Map(
        location=[c_lat, c_lon], zoom_start=4, crs="EPSG3857"
    )  # default web mercator crs

    folium.plugins.Fullscreen(
        position="topright",
        title="Expand me",
        title_cancel="Exit me",
        force_separate_button=True,
    ).add_to(m)

    # Google Basemap
    folium.TileLayer(
        tiles="http://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google",
        name="Google Satellite",
        overlay=False,
        control=True,
        show=True,
    ).add_to(m)
    # ESRI Basemap
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Esri Satellite",
        overlay=False,
        control=True,
        show=False,  # turn layer off
    ).add_to(m)
    # OpenStreetMap Basemap
    folium.TileLayer("openstreetmap", overlay=False, control=True, show=False).add_to(m)

    # Add COG layer if selected
    if cog_layer is not None and cog_layer in st.cog_layers:
        cog_s3uri = st.cog_layers[cog_layer]

        # Get the tile server URL from environment variable
        titiler_url = os.getenv("TITILER_API_URL", "http://stormlit-titiler")

        try:
            # First get COG statistics to determine min/max values for rescaling
            stats_url = f"{titiler_url}/cog/statistics"
            stats_response = requests.get(
                stats_url, params={"url": cog_s3uri}, timeout=30
            )
            stats_data = stats_response.json()
            st.session_state["cog_stats"] = stats_data

            # Get min/max values for rescaling
            min_value = stats_data["b1"]["min"]
            max_value = stats_data["b1"]["max"]

            # Get TileJSON for the COG
            tilejson_url = f"{titiler_url}/cog/WebMercatorQuad/tilejson.json"
            tilejson_response = requests.get(
                tilejson_url,
                params={
                    "url": cog_s3uri,
                    "rescale": f"{min_value},{max_value}",
                    "colormap_name": cmap_name,
                },
                timeout=10,
            )
            tilejson_data = tilejson_response.json()
            st.session_state[f"cog_tilejson_{cog_layer}"] = tilejson_data

            # Add the COG as a TileLayer to the map
            if "tiles" in tilejson_data:
                tile_url = tilejson_data["tiles"][0]
                folium_titiler_url = os.getenv(
                    "FOLIUM_TITILER_URL", "http://localhost:8000"
                )
                tile_url = tile_url.replace(titiler_url, folium_titiler_url)
                folium.TileLayer(
                    tiles=tile_url,
                    attr=f"COG: {cog_layer}",
                    name=cog_layer,
                    overlay=True,
                    control=True,
                    opacity=1,
                ).add_to(m)

                # zoom to the extent of the COG
                if "bounds" not in tilejson_data:
                    st.session_state[f"cog_error_{cog_layer}"] = (
                        "No bounds found in TileJSON response"
                    )
            else:
                st.session_state[f"cog_error_{cog_layer}"] = (
                    "No tiles found in TileJSON response"
                )

        except Exception as e:
            st.session_state[f"cog_error_{cog_layer}"] = str(e)

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
            fg_dams = add_circles_fg(df, sel_layers[idx], ["layer", "id"], "#e32636")
            fg_dams.add_to(m)
        elif key == "Gages":
            fg_gages = add_circles_fg(
                df, sel_layers[idx], ["layer", "site_no"], "#32cd32"
            )
            fg_gages.add_to(m)
        elif key == "Storms":
            fg_storms = add_circles_fg(
                df, sel_layers[idx], ["layer", "rank", "storm_type"], "#ed9121"
            )
            fg_storms.add_to(m)
        elif key == "Reference Lines":
            fg_ref_lines = add_polygons_fg(
                df, sel_layers[idx], ["layer", "id", "line_type"], style_ref_lines
            )
            fg_ref_lines.add_to(m)
        elif key == "Reference Points":
            fg_ref_points = add_markers_fg(
                df, sel_layers[idx], ["layer", "id", "point_type"], style_ref_points
            )
            fg_ref_points.add_to(m)
        else:
            pass
        idx += 1

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


def plot_ts(df: pd.DataFrame, var: str, st_col, title: Optional[str] = None):
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
    st_col : streamlit.columns
        The Streamlit column to place the plot in.
    title : Optional[str]
        The title of the plot. If None, a default title will be used.
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
    if title is None:
        title = f"Time Series Plot of {var}"
    fig = px.line(df, x="time", y=var, title=title)
    st_col.plotly_chart(fig)


def plot_ts_dual_y_axis(
    df: pd.DataFrame,
    var1: str,
    var2: str,
    st_col,
    title: Optional[str] = None,
):
    """Function for plotting time series data with dual y-axes.
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
    var1 : str
        The first variable to plot on the primary y-axis.
    var2 : str
        The second variable to plot on the secondary y-axis.
    st_col : streamlit.columns
        The Streamlit column to place the plot in.
    title : Optional[str]
        The title of the plot. If None, a default title will be used.
    """
    # Check if the DataFrame is empty
    if df.empty:
        st.warning("No data available for the selected variables.")
        return

    # Check if the required columns are present in the DataFrame
    required_columns = ["id", "time", var1, var2]
    if not all(col in df.columns for col in required_columns):
        st.error(f"DataFrame must contain the following columns: {required_columns}")
        return

    fig = go.Figure()

    # Add the first variable to the primary y-axis
    fig.add_trace(
        go.Scatter(
            x=df["time"],
            y=df[var1],
            mode="lines",
            name=var1,
            line=dict(color="blue"),
        )
    )

    # Add the second variable to the secondary y-axis
    fig.add_trace(
        go.Scatter(
            x=df["time"],
            y=df[var2],
            mode="lines",
            name=var2,
            line=dict(color="red"),
            yaxis="y2",
        )
    )

    # Update layout for dual y-axes
    fig.update_layout(
        title=title if title else f"Time Series Plot of {var1} and {var2}",
        xaxis_title="Time",
        yaxis=dict(
            title=var1,
            showgrid=False,
            zeroline=True,
        ),
        yaxis2=dict(
            title=var2,
            overlaying="y",
            side="right",
            showgrid=False,
            zeroline=True,
        ),
        legend=dict(x=0.75, y=1, traceorder="normal"),
    )

    st_col.plotly_chart(fig)


def plot_hist(df: pd.DataFrame, x_col: str, y_col: str, nbins: int):
    """
    Function for plotting histogram data.

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame containing the histogram data.
    x_col : str
        The column name for the x-axis values.
    y_col : str
        The column name for the y-axis values.
    nbins : int
        The number of bins for the histogram.
    """
    # Check if the DataFrame is empty
    if df.empty:
        st.warning("No data available for the selected variable.")
        return
    fig = px.histogram(
        df,
        nbins=nbins,
        x=x_col,
        y=y_col,
        title="Histogram of COG Values",
        labels={x_col: "COG Value", y_col: "Count"},
    )
    fig.update_traces(marker_color="blue")
    fig.update_layout(
        xaxis_title=x_col,
        yaxis_title=y_col,
        showlegend=True,
    )
    return fig
