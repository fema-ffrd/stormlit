import folium
import streamlit as st
import leafmap.foliumap as leafmap
import geopandas as gpd
from shapely.geometry import shape
import xarray as xr
import numpy as np
import matplotlib.cm as cm
from rasterio.crs import CRS
from rasterio.warp import transform_bounds


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


@st.cache_data(show_spinner=False)
def _prepare_rgba_image(
    image_data: np.ndarray, cmap_name: str = "Spectral_r"
) -> np.ndarray | None:
    """Convert precipitation totals into an RGBA image for folium overlays.

    Parameters
    ----------
    image_data : np.ndarray
        The input image data array.
    cmap_name : str, optional
        The name of the matplotlib colormap to use. Default is "Spectral_r".

    Returns
    -------
    np.ndarray | None
        The RGBA image array or None if input is empty or invalid.
    """
    if image_data.size == 0:
        return None
    finite_mask = np.isfinite(image_data)
    if not finite_mask.any():
        return None
    valid_data = image_data[finite_mask]
    min_val = float(valid_data.min())
    max_val = float(valid_data.max())
    if np.isclose(max_val, min_val):
        normalized = np.zeros_like(image_data, dtype=float)
    else:
        normalized = (image_data - min_val) / (max_val - min_val)
    normalized = np.clip(np.nan_to_num(normalized, nan=0.0), 0.0, 1.0)
    cmap = cm.get_cmap(cmap_name)
    rgba = (cmap(normalized) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(finite_mask, rgba[..., 3], 0)
    return rgba


def _compute_overlay_bounds(da: xr.DataArray):
    """Compute the bounding box for the storm overlay based on the coordinates of the DataArray.

    Parameters
    ----------
    da : xr.DataArray
        The input DataArray for which to compute the overlay bounds.
    Returns
    -------
    list | None
        The bounding box [[south, west], [north, east]] or None if computation fails.
    """
    x_coord = _find_coord_name(da, ("lon", "longitude", "x"))
    y_coord = _find_coord_name(da, ("lat", "latitude", "y"))
    if x_coord is None or y_coord is None:
        return None
    x_vals = np.asarray(da[x_coord].values)
    y_vals = np.asarray(da[y_coord].values)
    if x_vals.size == 0 or y_vals.size == 0:
        return None
    if np.isnan(x_vals).all() or np.isnan(y_vals).all():
        return None
    min_x, max_x = float(np.nanmin(x_vals)), float(np.nanmax(x_vals))
    min_y, max_y = float(np.nanmin(y_vals)), float(np.nanmax(y_vals))
    source_bounds = (min_x, min_y, max_x, max_y)
    crs = _extract_crs(da)
    if crs is None or crs.to_epsg() == 4326:
        return [[min_y, min_x], [max_y, max_x]]
    try:
        west, south, east, north = transform_bounds(
            crs,
            "EPSG:4326",
            *source_bounds,
            densify_pts=21,
        )
    except Exception as exc:
        st.warning(f"Failed to transform storm bounds to WGS84: {exc}")
        return None
    return [[south, west], [north, east]]


def _extract_crs(da: xr.DataArray):
    """Extract the CRS (Coordinate Reference System) from a DataArray.

    Parameters
    ----------
    da : xr.DataArray
        The input DataArray from which to extract the CRS.
    Returns
    -------
    CRS | None
        The extracted CRS object or None if extraction fails.
    """
    try:
        crs = da.rio.crs  # type: ignore[attr-defined]
        if crs:
            return CRS.from_user_input(crs)
    except Exception:
        pass
    candidate = da.attrs.get("crs") or da.attrs.get("spatial_ref")
    if not candidate and "spatial_ref" in da.coords:
        candidate = da.spatial_ref.attrs.get("spatial_ref")
    if candidate:
        try:
            return CRS.from_user_input(candidate)
        except Exception:
            return None
    return None


def _find_coord_name(da: xr.DataArray, candidates) -> str | None:
    for name in candidates:
        if name in da.coords:
            return name
    return None


def add_storm_layer(m: leafmap.Map, storm_id: int | None) -> None:
    """Add storm overlay to the map from IceChunk dataset

    Parameters
    ----------
        m (leafmap.Map): The leafmap map object to add the overlay to.
        storm_id (int | None): The storm ID to retrieve the overlay for.
    Returns
    -------
        None
    """
    storm_data = st.session_state.get("hydromet_storm_data")
    if storm_id is None or storm_data is None:
        return
    bounds = st.session_state.get("storm_bounds")
    st.session_state["storm_max"] = float(storm_data.values.max())
    st.session_state["storm_min"] = float(storm_data.values.min())
    if bounds is None:
        bounds = _compute_overlay_bounds(storm_data)
        if bounds is None:
            return
        st.session_state["storm_bounds"] = bounds

    rgba_image = _prepare_rgba_image(storm_data.values.astype(float))
    if rgba_image is None:
        return

    folium.raster_layers.ImageOverlay(
        image=rgba_image,
        bounds=bounds,
        opacity=0.75,
        name=f"Storm {storm_id}",
        interactive=False,
        cross_origin=False,
        zindex=1000,
    ).add_to(m)


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
    # Check if there's a focused feature position in session state
    focus_lat = st.session_state.get("single_event_focus_lat")
    focus_lon = st.session_state.get("single_event_focus_lon")
    focus_zoom = st.session_state.get("single_event_focus_zoom")

    if focus_lat is not None and focus_lon is not None and focus_zoom is not None:
        return focus_lat, focus_lon, focus_zoom

    # Otherwise, use default position based on layer
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
    elif map_layer == "MET":
        c_df = st.transpo.copy()
        if "lat" not in c_df.columns or "lon" not in c_df.columns:
            c_df["lat"] = c_df.geometry.centroid.y
            c_df["lon"] = c_df.geometry.centroid.x
        c_lat, c_lon = c_df["lat"].mean(), c_df["lon"].mean()
        c_zoom = 6
    else:
        raise ValueError(f"Invalid map layer {map_layer}. Choose 'HMS' or 'RAS'.")
    return c_lat, c_lon, c_zoom


def prep_metmap(
    zoom: int, c_lat: float, c_lon: float, storm_id: int | None
) -> leafmap.Map:
    """
    Prepare the leafmap map object based on the selected map layer.

    Parameters
    ----------
    zoom: int
        The initial zoom level for the map
    c_lat: float
        The center latitude for the map
    c_lon: float
        The center longitude for the map
    storm_id: int | None
        The storm ID to retrieve the overlay for, if applicable

    Returns
    -------
    leafmap.Map
        The prepared leafmap map object
    """
    m = leafmap.Map(
        locate_control=False,
        atlon_control=False,
        draw_export=False,
        draw_control=True,
        minimap_control=False,
        toolbar_control=False,
        layers_control=True,
        zoom_start=zoom,
    )

    # Add the layers to the map
    if st.transpo is not None:
        m.add_gdf(
            st.transpo,
            layer_name="Transposition Domain",
            info_mode="on_hover",
            style_function=lambda feature: {"fillColor": "#ff381e", "color": "#ff1e1e"},
            highlight_function=highlight_function,
            zoom_on_click=True,
            show=True,
        )
    if st.models is not None:
        m.add_gdf(
            st.models,
            layer_name="Models",
            info_mode="on_hover",
            fields=["model"],
            style_function=style_models,
            highlight_function=highlight_function,
            zoom_on_click=False,
            show=True,
        )
    if st.session_state["hydromet_storm_data"] is not None:
        add_storm_layer(m, storm_id)
        m.add_colorbar(
            colors=["blue", "cyan", "green", "yellow", "orange", "red"],
            caption="72-Hour Accumulated Precipitation (inches)",
            vmax=st.session_state["storm_max"],
            vmin=st.session_state["storm_min"],
        )
    m.clear_controls()
    m.set_center(c_lon, c_lat, zoom)

    return m


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
        locate_control=False,
        atlon_control=False,
        draw_export=False,
        draw_control=False,
        minimap_control=False,
        toolbar_control=False,
        layers_control=True,
        zoom_start=zoom,
    )

    # Add the layers to the map
    if st.models is not None:
        m.add_gdf(
            st.models,
            layer_name="Models",
            info_mode="on_hover",
            fields=["model"],
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
        m.set_center(c_lon, c_lat, zoom)

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
        locate_control=False,
        atlon_control=False,
        draw_export=False,
        draw_control=False,
        minimap_control=False,
        toolbar_control=False,
        layers_control=True,
        zoom_start=zoom,
        center=[c_lat, c_lon],  # Explicitly set center
    )

    # Add the layers to the map
    if st.subbasins is not None:
        m.add_gdf(
            st.subbasins,
            layer_name="Subbasins",
            info_mode="on_hover",
            fields=["hms_element"],
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
            fields=["hms_element"],
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
            fields=["hms_element"],
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
            fields=["hms_element"],
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
        m.set_center(c_lon, c_lat, zoom)
    return m


def get_hms_legend_stats(
    selected_gdf: gpd.GeoDataFrame, session_gdf: gpd.GeoDataFrame, filtered_gdf: str
):
    """
    Generate HMS model subbasin statistics for the map legend based on given geodataframe.
    Updates the session state with filtered geodataframe and their count.

    Parameters
    ----------
    selected_gdf: gpd.GeoDataFrame
        The GeoDataFrame containing the selected geometry.
    session_gdf: gpd.GeoDataFrame
        The GeoDataFrame containing geometries to filter subbasins.
    filtered_gdf: str
        The name of the filtered GeoDataFrame to update in session state.

    Returns
    -------
    num_subbasins: int
        The number of subbasins filtered and stored in session state.
    """
    if not selected_gdf.empty:
        model_geom = selected_gdf.geometry.iloc[0]
        centroids = session_gdf.geometry.centroid
        mask = centroids.within(model_geom)
        st.session_state[filtered_gdf] = session_gdf[mask].copy()
        st.session_state[filtered_gdf]["model"] = st.session_state["subbasin_id"]
        num_items = len(st.session_state[filtered_gdf])
    else:
        st.session_state[filtered_gdf] = None
        num_items = 0
    return num_items


def get_gis_legend_stats(
    session_gdf: gpd.GeoDataFrame,
    filtered_gdf: str,
    area_gdf: gpd.GeoDataFrame,
    area_col: str,
    target_id: str,
):
    """
    Generate GIS layer (gages and dams) statistics for the map legend based on given geodataframe.
    Updates the session state with filtered geodataframe and their count.

    Parameters
    ----------
    session_gdf: gpd.GeoDataFrame
        The GeoDataFrame containing geometries to filter subbasins.
        Example: st.gages for gages, st.dams for dams.
    filtered_: str
        The name of the filtered GeoDataFrame to update in session state.
        Example: "gages_filtered" for gages, "dams_filtered" for dams.
    area_gdf: gpd.GeoDataFrame
        The GeoDataFrame containing the area geometry to filter by.
        Example: st.subbasins for HMS subbasins, st.models for RAS models.
    area_col: str
        The column name for the area ID.
        Example: "hms_element" for HMS subbasins, "model" for RAS models.
    target_id: str
        The target area ID to filter by.
        Example: st.session_state["subbasin_id"] for HMS subbasins, st.session_state["model_id"] for RAS models.

    Returns
    -------
    num_items: int
        The number of items filtered and stored in session state.
    """
    st.session_state[filtered_gdf] = gpd.sjoin(
        session_gdf,
        area_gdf[area_gdf[area_col] == target_id],
        how="inner",
        predicate="intersects",
    )
    st.session_state[filtered_gdf]["lat"] = st.session_state[filtered_gdf]["lat_left"]
    st.session_state[filtered_gdf]["lon"] = st.session_state[filtered_gdf]["lon_left"]
    st.session_state[filtered_gdf]["index"] = st.session_state[filtered_gdf][
        "index_right"
    ]
    st.session_state[filtered_gdf]["layer"] = "Gages"
    st.session_state[filtered_gdf].drop(
        columns=[
            "lat_left",
            "lon_left",
            "lat_right",
            "lon_right",
            "layer_right",
            "layer_left",
            "index_right",
        ],
        inplace=True,
    )
    num_items = len(st.session_state[filtered_gdf])
    return num_items


def get_model_subbasin(
    geom: gpd.GeoSeries, session_gdf: gpd.GeoDataFrame, element_col: str
):
    """
    Get the HMS or RAS model subbasin ID that a provided geodataframe's geometry may be within.
    A subbasin refers to either an HMS or RAS model subbasin.

    Parameters
    ----------
    geom: gpd.GeoSeries
        The GeoSeries containing subbasin data.
    session_gdf: gpd.GeoDataFrame
        The GeoDataFrame containing subbasin geometries.
        Example: st.subbasins for HMS subbasins, st.models for RAS models.
    element_col: str
        The column name for the subbasin/model ID.
        Example: "hms_element" for HMS subbasins, "model" for RAS models.
    Returns
    -------
    subbasin_id: str
        The subbasin ID extracted from the GeoDataFrame.
    """
    # Get the centroids of the geometries in the GeoDataFrame
    centroid = geom.centroid
    # Check if the centroid is within any subbasin geometry
    mask = centroid.within(session_gdf.geometry)
    filtered_gdf = session_gdf[mask].copy()
    if not filtered_gdf.empty:
        subbasin_id = filtered_gdf.iloc[0][element_col]
        return subbasin_id


def get_gage_from_subbasin(subbasin_geom: gpd.GeoSeries):
    """
    Get the gage ID from a subbasin geometry.
    Determine if there are any gage points located within the subbasin polygon

    Parameters
    ----------
    subbasin_geom: gpd.GeoSeries
        A GeoSeries containing the geometry of the subbasin.

    Returns
    -------
    gage_id: str
        The gage ID if a gage is found within the subbasin, otherwise None
    """
    # Combine all subbasin geometries into one (if multiple)
    subbasin_geom = subbasin_geom.union_all
    # Get centroids of all gages
    gage_centroids = st.gages.centroid
    # Find which gage centroids are within the subbasin geometry
    mask = gage_centroids.within(subbasin_geom)
    filtered_gdf = st.gages[mask].copy()
    if not filtered_gdf.empty:
        return filtered_gdf["site_no"].tolist()
    else:
        return None


def get_gage_from_pt_ln(_geom: gpd.GeoSeries):
    """
    Get the gage ID from a point or line geometry.
    Determine if there are any gage points located within the reach line.

    Parameters
    ----------
    _geom: gpd.GeoSeries
        A GeoSeries containing the geometry of the point or line.

    Returns
    -------
    subbasin_id: str
        The subbasin ID if a subbasin is found containing the point or line, otherwise None
    """
    # Combine all geometries into one (if multiple)
    _geom = _geom.union_all.centroid
    # Get all subbasin geometries
    subbasin_geoms = st.subbasins.geometry
    # Find which subbasins contain the ln/pt geometry
    mask = subbasin_geoms.contains(_geom)
    filtered_gdf = st.subbasins[mask].copy()
    if filtered_gdf.empty:
        return None
    else:
        return get_gage_from_subbasin(filtered_gdf.geometry)


def get_gage_from_ref_ln(ref_id: str):
    """
    Identify the gage ID from a reference point or line ID.

    Parameters
    ----------
    ref_id: str
        The reference ID to extract the gage ID from.

    Returns
    -------
    tuple
        A tuple containing a boolean indicating if it is a gage and the gage ID if applicable.
    """
    is_gage = False
    gage_id = None
    if "gage" in ref_id:
        is_gage = True
        ref_id = ref_id.split("_")
        # find the index where usgs appears
        for idx, part in enumerate(ref_id):
            if "usgs" in part.lower():
                gage_idx = idx + 1
                gage_id = ref_id[gage_idx]
                return is_gage, gage_id
    else:
        return is_gage, gage_id


def focus_feature(
    item: dict,
    item_id: str,
    item_label: str,
    feature_type,
    map_click: bool = False,
):
    """
    Focus on a map feature by updating the session state with the item's details.

    Parameters
    ----------
    item: dict
        The item to focus on, containing its details.
    item_id: str
        The ID of the item.
    item_label: str
        The label of the item.
    feature_type: FeatureType or FeatureType
        The type of feature (Model, Gage, Dam, Reference Line, Reference Point, BC Line)
    map_click: bool
        Whether the focus was triggered by a map click or a button click.
    """
    geom = item.get("geometry", None)
    if geom and isinstance(geom, dict):
        # Convert dict to Geometry object if necessary
        geom = shape(geom)
    if geom:
        bounds = geom.bounds
        bbox = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
    else:
        bbox = None

    if "model" in item:
        st.session_state["model_id"] = item["model"]
    if "hms_element" in item:
        st.session_state["hms_element_id"] = item["hms_element"]
        st.session_state["subbasin_id"] = get_model_subbasin(
            geom, st.subbasins, "hms_element"
        )

    st.session_state.update(
        {
            "single_event_focus_feature_label": item_label,
            "single_event_focus_feature_id": item_id,
            "single_event_focus_lat": item.get("lat"),
            "single_event_focus_lon": item.get("lon"),
            # TODO: Add logic to determine zoom level based on item extent
            "single_event_focus_zoom": 12,
            "single_event_focus_bounding_box": bbox,
            "single_event_focus_feature_type": feature_type.value,
            "single_event_focus_map_click": map_click,
        }
    )
