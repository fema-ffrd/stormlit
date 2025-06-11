import os
import requests
import folium
import streamlit as st
import geopandas as gpd
import pandas as pd
from plotly import express as px
import plotly.graph_objects as go
from typing import Optional


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


def add_points_fg(
    gdf: gpd.GeoDataFrame,
    layer_name: str,
    tooltip_fields: list,
    color: str,
):
    """
    Add points to a folium map as a feature group

    Parameters
    ----------
    gdf: gpd.GeoDataFrame
        A GeoDataFrame with point geometries
    layer_name: str
        The name of the layer to add to the map
    tooltip_fields: list
        A list of fields to display in the tooltip
    color: str
        The color of the squares to be used as markers

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
            width: 10px;
            height: 10px">
        </div>
        """
    )

    fg_points = folium.FeatureGroup(name=layer_name)
    fg_points.add_child(
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
    return fg_points


def style_basins(feature):
    return {"fillColor": "#1e90ff"}

def style_ref_lines(feature):
    return {"color": "yellow", "weight": 4}

def style_bc_lines(feature):
    return {"color": "purple", "weight": 4}


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
        c_df = st.basins
        c_lat, c_lon = (
            c_df[c_df["NAME"] == layer_field]["lat"].mean(),
            c_df[c_df["NAME"] == layer_field]["lon"].mean(),
        )
        c_zoom = 10
    elif map_layer == "Gages":
        c_df = st.gages
        c_lat, c_lon = (
            c_df[c_df["site_no"] == layer_field]["lat"].mean(),
            c_df[c_df["site_no"] == layer_field]["lon"].mean(),
        )
        c_zoom = 14
    elif map_layer == "Dams":
        c_df = st.dams
        c_lat, c_lon = (
            c_df[c_df["id"] == layer_field]["lat"].mean(),
            c_df[c_df["id"] == layer_field]["lon"].mean(),
        )
        c_zoom = 14
    else:
        c_df = st.basins
        c_lat, c_lon = c_df["lat"].mean(), c_df["lon"].mean()
        c_zoom = 8
    return c_lat, c_lon, c_zoom


@st.cache_data
def prep_fmap(cog_layer: str = None) -> folium.Map:
    """
    Prep a folium map object given a geojson with a specificed basemap

    Parameters
    ----------
    cog_layer: str, optional
        The name of the COG layer to add to the map. If None, no COG layer is added.

    Returns
    -------
    folium.Map
        Folium map object
    """
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

    # Add the selected layers to the map
    if st.basins is not None:
        fg_basins = add_polygons_fg(
            st.basins, "Basins", ["HUC8", "NAME"], style_basins
        )
        fg_basins.add_to(m)
    if st.dams is not None:
        fg_dams = add_points_fg(st.dams, "Dams", ["id"], "#e32636")
        fg_dams.add_to(m)
    if st.gages is not None:
        fg_gages = add_points_fg(st.gages, "Gages", ["site_no"], "#32cd32")
        fg_gages.add_to(m)
    if st.ref_lines is not None:
        fg_ref_lines = add_polygons_fg(
            st.ref_lines, "Reference Lines", ["id", "model"], style_ref_lines
        )
        fg_ref_lines.add_to(m)
    if st.ref_points is not None:
        fg_ref_points = add_points_fg(
            st.ref_points, "Reference Points", ["id", "model"], "#e6870b"
        )
        fg_ref_points.add_to(m)
    if st.bc_lines is not None:
        fg_bc_lines = add_polygons_fg(
            st.bc_lines, "BC Lines", ["id", "model"], style_bc_lines
        )
        fg_bc_lines.add_to(m)

    # Add COG layer if selected
    if cog_layer is not None:
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
            st.session_state[f"cog_stats_{cog_layer}"] = stats_data

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
                    "colormap_name": "viridis",
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
                if "bounds" in tilejson_data:
                    bounds = tilejson_data["bounds"]
                    m.fit_bounds(
                        [
                            [bounds[1], bounds[0]],
                            [bounds[3], bounds[2]],
                        ]
                    )
                else:
                    st.session_state[f"cog_error_{cog_layer}"] = (
                        "No bounds found in TileJSON response"
                    )
            else:
                st.session_state[f"cog_error_{cog_layer}"] = (
                    "No tiles found in TileJSON response"
                )

        except Exception as e:
            st.session_state[f"cog_error_{cog_layer}"] = str(e)
    else:
        pass

    # Add the layer control to the map
    folium.LayerControl().add_to(m)
    return m
