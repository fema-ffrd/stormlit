import os
import requests
import folium
import streamlit as st
import pandas as pd
import geopandas as gpd


def highlight_function(feature):
    return {
        "fillColor": "yellow",
        "color": "black",
        "weight": 3,
        "opacity": 0.5,
    }


def add_polygons(
    fmap: folium.Map,
    gdf: gpd.GeoDataFrame,
    layer_name: str,
    tooltip_fields: list,
    style_function: callable,
    show_layer: bool = True,
):
    """
    Add polygons to a folium map as a layer

    Parameters
    ----------
    fmap: folium.Map
        The folium map object to add the polygons to
    gdf: gpd.GeoDataFrame
        A GeoDataFrame with polygon geometries
    layer_name: str
        The name of the layer to add to the map
    tooltip_fields: list
        A list of fields to display in the tooltip
    style_function: callable
        A function to style the polygons
    show_layer: bool
        Whether to show the layer by default
    Returns
    -------
    None

    """
    gdf["geometry"] = gdf["geometry"].simplify(tolerance=0.001)
    folium.GeoJson(
        gdf,
        name=layer_name,
        zoom_on_click=True,
        style_function=style_function,
        highlight_function=highlight_function,
        tooltip=folium.GeoJsonTooltip(fields=tooltip_fields),
        popup=folium.GeoJsonPopup(fields=tooltip_fields),
        popup_keep_highlighted=True,
        show=show_layer,
    ).add_to(fmap)


def add_squares(
    fmap: folium.Map,
    gdf: gpd.GeoDataFrame,
    layer_name: str,
    tooltip_fields: list,
    color: str,
):
    """
    Add points to a folium map as a layer

    Parameters
    ----------
    fmap: folium.Map
        The folium map object to add the points to
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
    None
    """
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
    folium.GeoJson(
        gdf,
        name=layer_name,
        marker=folium.Marker(icon=div_icon),
        tooltip=folium.GeoJsonTooltip(fields=tooltip_fields),
        popup=folium.GeoJsonPopup(fields=tooltip_fields),
        popup_keep_highlighted=True,
        highlight_function=highlight_function,
        zoom_on_click=True,
    ).add_to(fmap)


def add_circles(
    fmap: folium.Map,
    gdf: gpd.GeoDataFrame,
    layer_name: str,
    tooltip_fields: list,
    color: str,
):
    """
    Add circles to a folium map as a layer

    Parameters
    ----------
    fmap: folium.Map
        The folium map object to add the circles to
    gdf: gpd.GeoDataFrame
        A GeoDataFrame with point geometries
    layer_name: str
        The name of the layer to add to the map
    tooltip_fields: list
        A list of fields to display in the tooltip
    color: str
        The color of the circles to be used as markers
    Returns
    -------
    None
    """
    folium.GeoJson(
        gdf,
        name=layer_name,
        marker=folium.CircleMarker(
            radius=5,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=1,
        ),
        tooltip=folium.GeoJsonTooltip(fields=tooltip_fields),
        popup=folium.GeoJsonPopup(fields=tooltip_fields),
        popup_keep_highlighted=True,
        highlight_function=highlight_function,
        zoom_on_click=True,
    ).add_to(fmap)


def style_bc_lines(feature):
    return {"color": "#e21426", "weight": 4}


def style_ref_lines(feature):
    return {"color": "brown", "weight": 4}


def style_models(feature):
    return {"fillColor": "#32cd32"}


def style_subbasins(feature):
    return {"fillColor": "#1e90ff"}


def style_reaches(feature):
    return {"color": "#8f44cc", "weight": 4}


def style_reservoirs(feature):
    return {"fillColor": "#0a0703", "weight": 4}


def get_map_pos(map_layer: str):
    """
    Get the map position based on the selected layer and field.

    Parameters
    ----------
    map_layer: str
        The selected map layer. One of "HMS" or "RAS".
    Returns
    -------
    tuple
        A tuple containing the latitude, longitude, and zoom level
    """
    if map_layer == "HMS":
        c_df = st.subbasins
        if "lat" not in c_df.columns or "lon" not in c_df.columns:
            c_df["lat"] = c_df.geometry.centroid.y
            c_df["lon"] = c_df.geometry.centroid.x
        c_lat, c_lon = c_df["lat"].mean(), c_df["lon"].mean()
        c_zoom = 8
    elif map_layer == "RAS":
        c_df = st.models
        if "lat" not in c_df.columns or "lon" not in c_df.columns:
            c_df["lat"] = c_df.geometry.centroid.y
            c_df["lon"] = c_df.geometry.centroid.x
        c_lat, c_lon = c_df["lat"].mean(), c_df["lon"].mean()
        c_zoom = 8
    else:
        raise ValueError(f"Invalid map layer {map_layer}. Choose 'HMS' or 'RAS'.")
    return c_lat, c_lon, c_zoom


@st.cache_data
def prep_fmap(
    c_lat: float, c_lon: float, zoom: int, map_type: str, cog_layer: str = None
) -> folium.Map:
    """
    Prep a folium map object given a geojson with a specificed basemap

    Parameters
    ----------
    c_lat: float
        The latitude to center the map on
    c_lon: float
        The longitude to center the map on
    zoom: int
        The initial zoom level for the map
    map_type: str
        The type of map to create, either "HMS", "RAS", or "All
    cog_layer: str, optional
        The name of the COG layer to add to the map. If None, no COG layer is added.

    Returns
    -------
    folium.Map
        Folium map object
    """
    # Create a folium map centered at the mean latitude and longitude
    m = folium.Map(
        location=[c_lat, c_lon], zoom_start=zoom, crs="EPSG3857"
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
        show=False,
    ).add_to(m)

    # RAS Elements
    if map_type == "RAS" or map_type == "All":
        # Add the layers to the map
        if st.models is not None:
            add_polygons(m, st.models, "Models", ["model"], style_models)
        if st.bc_lines is not None:
            add_polygons(m, st.bc_lines, "BC Lines", ["id", "model"], style_bc_lines)
        if st.ref_points is not None:
            add_squares(
                m, st.ref_points, "Reference Points", ["id", "model"], "#e6870b"
            )
        if st.ref_lines is not None:
            add_polygons(
                m, st.ref_lines, "Reference Lines", ["id", "model"], style_ref_lines
            )
    # HMS Elements
    if map_type == "HMS" or map_type == "All":
        if st.subbasins is not None:
            add_polygons(
                m,
                st.subbasins,
                "Subbasins",
                ["hms_element", "layer"],
                style_function=style_subbasins,
            )
        if st.reaches is not None:
            add_polygons(
                m,
                st.reaches,
                "Reaches",
                ["hms_element", "layer"],
                style_function=style_reaches,
            )
        if st.junctions is not None:
            add_squares(
                m, st.junctions, "Junctions", ["hms_element", "layer"], "#70410c"
            )
        if st.reservoirs is not None:
            add_squares(
                m, st.reservoirs, "Reservoirs", ["hms_element", "layer"], "#0a0703"
            )

    # Additional Elements
    if st.dams is not None:
        add_circles(m, st.dams, "Dams", ["id"], "#e21426")
    if st.gages is not None:
        add_circles(m, st.gages, "Gages", ["site_no"], "#32cd32")

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
            st.session_state["cog_stats"] = stats_data["b1"]
            st.session_state["cog_hist"] = pd.DataFrame(stats_data["b1"]["histogram"]).T

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
            st.session_state["cog_tilejson"] = tilejson_data

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
                    st.session_state["cog_error"] = (
                        "No bounds found in TileJSON response"
                    )
            else:
                st.session_state["cog_error"] = "No tiles found in TileJSON response"

        except Exception as e:
            st.session_state["cog_error"] = str(e)

    # Add the layer control to the map
    folium.LayerControl().add_to(m)
    return m
