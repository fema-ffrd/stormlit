import folium
import streamlit as st
import leafmap.foliumap as leafmap


def highlight_function(feature):
    return {
        "fillColor": "red",
        "color": "red",
        "weight": 3,
        "opacity": 0.9,
    }


def style_bc_lines(feature):
    return {"color": "#e21426", "weight": 4}


def style_ref_lines(feature):
    return {"color": "brown", "weight": 4}


def style_models(feature):
    return {"fillColor": "#1e90ff"}


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
        c_df = st.subbasins.copy()
        if "lat" not in c_df.columns or "lon" not in c_df.columns:
            c_df["lat"] = c_df.geometry.centroid.y
            c_df["lon"] = c_df.geometry.centroid.x
        c_lat, c_lon = c_df["lat"].mean(), c_df["lon"].mean()
        c_zoom = 8
    elif map_layer == "RAS":
        c_df = st.models.copy()
        if "lat" not in c_df.columns or "lon" not in c_df.columns:
            c_df["lat"] = c_df.geometry.centroid.y
            c_df["lon"] = c_df.geometry.centroid.x
        c_lat, c_lon = c_df["lat"].mean(), c_df["lon"].mean()
        c_zoom = 8
    else:
        raise ValueError(f"Invalid map layer {map_layer}. Choose 'HMS' or 'RAS'.")
    return c_lat, c_lon, c_zoom


def prep_rasmap(bounds: list, zoom: int, c_lat: float, c_lon: float) -> leafmap.Map:
    """
    Prepare the leafmap map object based on the selected map layer.

    Parameters
    ----------
    bounds: list
        The bounding box to zoom to [[min_lon, min_lat], [max_lon, max_lat]]
    zoom: int
        The initial zoom level for the map
    c_lat: float
        The center latitude for the map
    c_lon: float
        The center longitude for the map

    Returns
    -------
    leafmap.Map
        The prepared leafmap map object
    """
    m = leafmap.Map(
        locate_control=True,
        atlon_control=True,
        draw_export=True,
        minimap_control=False,
        zoom_start=zoom,
    )

    # Add the layers to the map
    if st.models is not None:
        m.add_gdf(
            st.models,
            layer_name="Models",
            info_mode="on_hover",
            style_function=style_models,
            highlight_function=highlight_function,
            zoom_on_click=True,
            show=True,
        )
    if st.bc_lines is not None:
        m.add_gdf(
            st.bc_lines,
            layer_name="BC Lines",
            info_mode="on_hover",
            style_function=style_bc_lines,
            highlight_function=highlight_function,
            zoom_on_click=True,
            show=True,
        )
    if st.ref_points is not None:
        color = "#e6870b"
        rt_pt_div_icon = folium.DivIcon(
            html=f"""
            <div style="
                background-color: {color};
                border: 1px solid black;
                width: 10px;
                height: 10px">
            </div>
            """
        )
        m.add_gdf(
            st.ref_points,
            layer_name="Reference Points",
            info_mode="on_hover",
            marker=folium.Marker(icon=rt_pt_div_icon),
            highlight_function=highlight_function,
            zoom_on_click=True,
            show=True,
        )
    if st.ref_lines is not None:
        m.add_gdf(
            st.ref_lines,
            layer_name="Reference Lines",
            info_mode="on_hover",
            fields=["id", "model"],
            style_function=style_ref_lines,
            highlight_function=highlight_function,
            zoom_on_click=True,
            show=True,
        )

    # Additional Elements
    if st.dams is not None:
        color = "#e21426"
        dams_div_icon = folium.DivIcon(
            html=f"""
            <div style="
                background-color: {color};
                border: 1px solid black;
                width: 10px;
                height: 10px">
            </div>
            """
        )
        m.add_gdf(
            st.dams,
            layer_name="Dams",
            info_mode="on_hover",
            fields=["id"],
            marker=folium.Marker(icon=dams_div_icon),
            highlight_function=highlight_function,
            zoom_on_click=True,
            show=True,
        )
    if st.gages is not None:
        color = "#32cd32"
        gage_div_icon = folium.DivIcon(
            html=f"""
            <div style="
                background-color: {color};
                border: 1px solid black;
                width: 10px;
                height: 10px">
            </div>
            """
        )
        m.add_gdf(
            st.gages,
            layer_name="Gages",
            info_mode="on_hover",
            fields=["site_no"],
            marker=folium.Marker(icon=gage_div_icon),
            highlight_function=highlight_function,
            zoom_on_click=True,
            show=True,
        )

    if bounds is not None:
        # bounds is in format [[lat, lon], [lat, lon]] from folium/focus_feature
        # Need to convert to [min_lon, min_lat, max_lon, max_lat] for leafmap
        lat1, lon1 = bounds[0]
        lat2, lon2 = bounds[1]
        min_lat, max_lat = min(lat1, lat2), max(lat1, lat2)
        min_lon, max_lon = min(lon1, lon2), max(lon1, lon2)
        bbox = [min_lon, min_lat, max_lon, max_lat]
        m.zoom_to_bounds(bbox)
    else:
        m.set_center(c_lon, c_lat, zoom=8)

    return m


def prep_hmsmap(bounds: list, zoom: int, c_lat: float, c_lon: float) -> leafmap.Map:
    """
    Prepare the leafmap map object based on the selected map layer.

    Parameters
    ----------
    bounds: list
        The bounding box to zoom to [[min_lon, min_lat], [max_lon, max_lat]]
    zoom: int
        The initial zoom level for the map
    c_lat: float
        The center latitude for the map
    c_lon: float
        The center longitude for the map

    Returns
    -------
    leafmap.Map
        The prepared leafmap map object
    """
    m = leafmap.Map(
        locate_control=True,
        atlon_control=True,
        draw_export=True,
        minimap_control=False,
        zoom_start=zoom,
    )

    # Add the layers to the map
    if st.subbasins is not None:
        m.add_gdf(
            st.subbasins,
            layer_name="Subbasins",
            info_mode="on_hover",
            style_function=style_subbasins,
            highlight_function=highlight_function,
            zoom_on_click=True,
            show=True,
        )
    if st.reaches is not None:
        m.add_gdf(
            st.reaches,
            layer_name="Reaches",
            info_mode="on_hover",
            style_function=style_reaches,
            highlight_function=highlight_function,
            zoom_on_click=True,
            show=True,
        )
    if st.junctions is not None:
        color = "#70410c"
        junctions_div_icon = folium.DivIcon(
            html=f"""
            <div style="
                background-color: {color};
                border: 1px solid black;
                width: 10px;
                height: 10px">
            </div>
            """
        )
        m.add_gdf(
            st.junctions,
            layer_name="Junctions",
            info_mode="on_hover",
            marker=folium.Marker(icon=junctions_div_icon),
            highlight_function=highlight_function,
            zoom_on_click=True,
            show=True,
        )
    if st.reservoirs is not None:
        color = "#0a0703"
        reservoirs_div_icon = folium.DivIcon(
            html=f"""
            <div style="
                background-color: {color};
                border: 1px solid black;
                width: 10px;
                height: 10px">
            </div>
            """
        )
        m.add_gdf(
            st.reservoirs,
            layer_name="Reservoirs",
            info_mode="on_hover",
            marker=folium.Marker(icon=reservoirs_div_icon),
            highlight_function=highlight_function,
            zoom_on_click=True,
            show=True,
        )

    # Additional Elements
    if st.dams is not None:
        color = "#e21426"
        dams_div_icon = folium.DivIcon(
            html=f"""
            <div style="
                background-color: {color};
                border: 1px solid black;
                width: 10px;
                height: 10px">
            </div>
            """
        )
        m.add_gdf(
            st.dams,
            layer_name="Dams",
            info_mode="on_hover",
            fields=["id"],
            marker=folium.Marker(icon=dams_div_icon),
            highlight_function=highlight_function,
            zoom_on_click=True,
            show=True,
        )
    if st.gages is not None:
        color = "#32cd32"
        gage_div_icon = folium.DivIcon(
            html=f"""
            <div style="
                background-color: {color};
                border: 1px solid black;
                width: 10px;
                height: 10px">
            </div>
            """
        )
        m.add_gdf(
            st.gages,
            layer_name="Gages",
            info_mode="on_hover",
            fields=["site_no"],
            marker=folium.Marker(icon=gage_div_icon),
            highlight_function=highlight_function,
            zoom_on_click=True,
            show=True,
        )

    if bounds is not None:
        # bounds is in format [[lat, lon], [lat, lon]] from folium/focus_feature
        # Need to convert to [min_lon, min_lat, max_lon, max_lat] for leafmap
        lat1, lon1 = bounds[0]
        lat2, lon2 = bounds[1]
        min_lat, max_lat = min(lat1, lat2), max(lat1, lat2)
        min_lon, max_lon = min(lon1, lon2), max(lon1, lon2)
        bbox = [min_lon, min_lat, max_lon, max_lat]
        m.zoom_to_bounds(bbox)
    else:
        m.set_center(c_lon, c_lat, zoom=8)
    return m
