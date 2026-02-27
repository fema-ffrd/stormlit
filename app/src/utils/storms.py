import base64
import io
import json
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from uuid import uuid4

import numpy as np
import xarray as xr
import streamlit as st
from contextlib import nullcontext
from pyproj import CRS, Transformer
from pyproj.exceptions import ProjError
import matplotlib.pyplot as plt
import geopandas as gpd
from PIL import Image
from matplotlib.animation import FuncAnimation

from db.icechunk import (
    open_repo,
    open_session,
)

TransformerGroup = None
WGS84 = CRS.from_epsg(4326)

def _project_cube(da: xr.DataArray) -> xr.DataArray:
    """Project a DataArray to WGS84.

    Parameters
    ----------
    da : xr.DataArray
        The input DataArray to project.

    Returns
    -------
    xr.DataArray
        The projected DataArray.
    """
    # Assign the cube's native CRS and reproject to WGS84 for clipping
    native_crs = da.rio.crs or _resolve_dataset_crs(da)
    if native_crs is not None:
        da = da.rio.write_crs(native_crs)
    else:
        native_crs = WGS84
        da = da.rio.write_crs(native_crs)

    if native_crs != WGS84:
        res_x, res_y = da.rio.resolution()
        bounds = da.rio.bounds()
        sample_x = bounds[0]
        sample_y = bounds[1]
        try:
            to_wgs84 = Transformer.from_crs(native_crs, WGS84, always_xy=True)
            lon0, lat0 = to_wgs84.transform(sample_x, sample_y)
            lon1, _ = to_wgs84.transform(sample_x + res_x, sample_y)
            _, lat2 = to_wgs84.transform(sample_x, sample_y + res_y)
            deg_res_x = abs(lon1 - lon0)
            deg_res_y = abs(lat2 - lat0)
            deg_res_x = deg_res_x if np.isfinite(deg_res_x) and deg_res_x > 0 else 0.01
            deg_res_y = deg_res_y if np.isfinite(deg_res_y) and deg_res_y > 0 else 0.01
            resolution = (min(deg_res_x, 1.0), min(deg_res_y, 1.0))
        except Exception:
            resolution = (0.01, 0.01)
        da = da.rio.reproject(
            "EPSG:4326",
            resolution=resolution,
            nodata=np.nan,
        )
        return da


def compute_storm(
    storm_id: int,
    aorc_storm_href: str,
    tab: st.delta_generator.DeltaGenerator | None = None,
) -> None:
    """
    Compute storm precipitation from the FFRD dataset.

    Parameters
    ----------
    storm_id: int
        The ID of the storm to compute.
    aorc_storm_href: str
        The icechunk s3 href for the storm to reference.
    tab: st.delta_generator.DeltaGenerator, optional
        The Streamlit tab to display progress (default is None).
    Returns
    -------
    None
    """
    # split the aorc_storm_href into bucket and prefix
    bucket, prefix = aorc_storm_href.replace("s3://", "").split("/", 1)
    repo = open_repo(bucket=bucket, prefix=prefix)
    ds = open_session(repo=repo, branch="main")
    last_anim_storm = st.session_state.get("storm_animation_storm_id")
    if last_anim_storm != storm_id:
        st.session_state["storm_animation_payload"] = None
        st.session_state["storm_animation_html"] = None
        st.session_state["storm_animation_requested"] = False
        st.session_state["storm_animation_storm_id"] = storm_id
    if storm_id != st.session_state.get("storm_cache"):
        parent_ctx = tab if tab is not None else nullcontext()
        with parent_ctx:
            with st.spinner(
                f"Computing 72-hour total precipitation for Storm ID: {storm_id}..."
            ):
                ds_storm = ds.sel(storm_id=storm_id)
                if "APCP_surface" not in ds_storm:
                    raise ValueError(
                        "Dataset does not contain 'APCP_surface' variable."
                    )
                da_precip = ds_storm["APCP_surface"]
                if "time" not in da_precip.dims:
                    raise ValueError(
                        "'APCP_surface' variable does not have 'time' dimension."
                    )
                # Load cube into memory and convert mm to inches
                precip_cube = _load_precip_cube(da_precip)
                # Aggregate to 72-hour accumulated precip
                total_precip = precip_cube.sum(dim="time")
                # Reproject the cube to EPSG:4326
                total_precip = _project_cube(total_precip)
                # Store the bounds of the storm. Format to [[south, west], [north, east]]
                storm_bounds = total_precip.rio.bounds()
                storm_bounds = [[storm_bounds[1], storm_bounds[0]], [storm_bounds[3], storm_bounds[2]]]
                # Clip the storm to the transposition domain
                target_crs = total_precip.rio.crs
                transposed_geom = st.transpo.to_crs(target_crs).geometry.values[0]
                clipped_precip = total_precip.rio.clip([transposed_geom], drop=True, all_touched=True)
                # Store the bounds of the clipped storm. Format to [[south, west], [north, east]]
                clipped_storm_bounds = clipped_precip.rio.bounds()
                clipped_storm_bounds = [[clipped_storm_bounds[1], clipped_storm_bounds[0]], [clipped_storm_bounds[3], clipped_storm_bounds[2]]]
                # Update session state
                st.session_state["storm_bounds"] = storm_bounds
                st.session_state["clipped_storm_bounds"] = clipped_storm_bounds
                st.session_state["hydromet_storm_data"] = clipped_precip
                st.session_state["storm_cache"] = storm_id


def compute_hyetograph(
    storm_id: int,
    aorc_storm_href: str,
    lat: float,
    lon: float,
    tab: st.delta_generator.DeltaGenerator | None = None,
) -> None:
    """
    Compute a hyetograph for a given point from the FFRD dataset.

    Parameters
    ----------
        storm_id (int): The ID of the storm to compute.
        aorc_storm_href (str): The icechunk s3 href for the storm to reference.
        lat (float): The latitude of the point.
        lon (float): The longitude of the point.
        tab (st.delta_generator.DeltaGenerator): The Streamlit tab to display progress.
    Returns
    -------
    None
    """
    if lat is None or lon is None or storm_id is None:
        return
    bucket, prefix = aorc_storm_href.replace("s3://", "").split("/", 1)
    repo = open_repo(bucket=bucket, prefix=prefix)
    ds = open_session(repo=repo, branch="main")
    parent_ctx = tab if tab is not None else nullcontext()
    with parent_ctx:
        with st.spinner(f"Computing hyetograph for point ({lat}, {lon})..."):
            ds_storm = ds.sel(storm_id=storm_id)
            proj_x, proj_y = _project_lonlat_to_dataset(ds_storm, lon, lat)
            sel_kwargs = {"x": proj_x, "y": proj_y}
            ds_point = ds_storm.sel(sel_kwargs, method="nearest")
            if "APCP_surface" not in ds_point:
                raise ValueError("Dataset does not contain 'APCP_surface' variable.")
            da_precip = ds_point["APCP_surface"]
            if "time" not in da_precip.dims:
                raise ValueError(
                    "'APCP_surface' variable does not have 'time' dimension."
                )
            precip_point = _load_precip_cube(da_precip)
            st.session_state["hyeto_cache"][(lat, lon, storm_id)] = precip_point


def compute_storm_animation(
    storm_id: int | None,
    aorc_storm_href: str,
) -> None:
    """
    Compute per-timestep precipitation frames for animation.

    Parameters
    ----------
    storm_id: int
        The ID of the storm to compute the animation for.
    aorc_storm_href: str
        The icechunk s3 href for the storm to reference.

    Returns
    -------
    None
    """
    if storm_id is None:
        st.info("Select a storm before generating an animation.")
        return

    bucket, prefix = aorc_storm_href.replace("s3://", "").split("/", 1)
    repo = open_repo(bucket=bucket, prefix=prefix)
    ds = open_session(repo=repo, branch="main")
    ds_storm = ds.sel(storm_id=storm_id)
    if "APCP_surface" not in ds_storm:
        raise ValueError("Dataset does not contain 'APCP_surface' variable.")
    da_precip = ds_storm["APCP_surface"]
    if "time" not in da_precip.dims:
        raise ValueError("'APCP_surface' variable does not have 'time' dimension.")
    precip_cube = _load_precip_cube(da_precip)
    precip_cube = _project_cube(precip_cube)
    precip_cube = _orient_cube_north_up(precip_cube)
    st.session_state["storm_animation_payload"] = _animation_payload_from_cube(
        precip_cube
    )


def _coerce_crs_input(value: object) -> object | None:
    """Normalize CRS metadata that may arrive as raw bytes."""
    if value is None or isinstance(value, CRS):
        return value

    if isinstance(value, (bytes, bytearray, np.bytes_)):
        raw = bytes(value)
        for encoding in ("utf-8", "cp1252", "latin-1"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="ignore")

    return value


def _resolve_dataset_crs(ds: xr.Dataset) -> CRS | None:
    """Attempt to resolve the dataset's CRS from common locations and formats."""

    def _attempt(value):
        normalized = _coerce_crs_input(value)
        if normalized is None:
            return None
        try:
            return CRS.from_user_input(normalized)
        except Exception:
            return None

    data_var = ds["APCP_surface"] if "APCP_surface" in ds else None
    if data_var is not None:
        try:
            crs_val = data_var.rio.crs  # type: ignore[attr-defined]
            if crs_val:
                crs_obj = _attempt(crs_val)
                if crs_obj:
                    return crs_obj
        except Exception:
            pass
        for key in ("spatial_ref", "crs_wkt", "crs"):
            val = data_var.attrs.get(key)
            if val:
                crs_obj = _attempt(val)
                if crs_obj:
                    return crs_obj

    if "spatial_ref" in ds.coords:
        attrs = ds.coords["spatial_ref"].attrs
        for key in ("spatial_ref", "crs_wkt", "crs"):
            val = attrs.get(key)
            if val:
                crs_obj = _attempt(val)
                if crs_obj:
                    return crs_obj

    if "crs" in ds.attrs:
        crs_obj = _attempt(ds.attrs["crs"])
        if crs_obj:
            return crs_obj

    return None


def _horizontal_crs(crs: CRS) -> CRS:
    """Return the horizontal component of a CRS (projected/geographic)."""
    if crs.is_geographic or crs.is_projected:
        return crs

    if crs.sub_crs_list:
        for candidate in crs.sub_crs_list:
            horiz = _horizontal_crs(candidate)
            if horiz.is_geographic or horiz.is_projected:
                return horiz

    base = crs.source_crs or crs.base_crs
    if base is not None:
        horiz = _horizontal_crs(base)
        if horiz.is_geographic or horiz.is_projected:
            return horiz

    return crs


def _transform_point(
    src_crs: CRS,
    dst_crs: CRS,
    x: float,
    y: float,
) -> tuple[tuple[float, float] | None, Exception | None]:
    """Transform a point between two CRSs, returning the last error if all pipelines fail."""
    if src_crs == dst_crs:
        return (float(x), float(y)), None

    transformers: list[Transformer] = []
    last_error: Exception | None = None

    for allow_ballpark in (False, True):
        try:
            transformers.append(
                Transformer.from_crs(
                    src_crs,
                    dst_crs,
                    always_xy=True,
                    allow_ballpark=allow_ballpark,
                )
            )
        except ProjError as exc:
            last_error = exc

    for transformer in transformers:
        try:
            tx, ty = transformer.transform(x, y)
        except ProjError as exc:
            last_error = exc
            continue

        if np.isfinite(tx) and np.isfinite(ty):
            return (float(tx), float(ty)), None

    return None, last_error


def _project_lonlat_to_dataset(
    ds: xr.Dataset,
    lon: float,
    lat: float,
) -> tuple[float, float]:
    """Project a lon/lat pair to the dataset's native CRS coordinates."""
    try:
        lon = float(lon)
        lat = float(lat)
    except (TypeError, ValueError) as exc:
        raise ValueError("Longitude and latitude must be numeric values.") from exc

    if not (np.isfinite(lon) and np.isfinite(lat)):
        raise ValueError("Longitude and latitude must be finite values.")

    dataset_crs = _resolve_dataset_crs(ds)
    if dataset_crs is None:
        dims = set(ds.dims.keys()) if isinstance(ds.dims, dict) else set(ds.dims)
        lon_like = {"lon", "longitude"}
        lat_like = {"lat", "latitude"}
        if dims & lon_like and dims & lat_like:
            return lon, lat
        raise ValueError("Unable to determine dataset CRS for projection.")

    target_crs = _horizontal_crs(dataset_crs)
    geodetic_crs = target_crs.geodetic_crs or (
        target_crs if target_crs.is_geographic else None
    )

    errors: list[str] = []

    lon_geo, lat_geo = lon, lat
    if geodetic_crs is not None and geodetic_crs != WGS84:
        geo_result, geo_err = _transform_point(WGS84, geodetic_crs, lon, lat)
        if geo_result is None:
            errors.append(f"WGS84→{geodetic_crs.to_string()} failed: {geo_err}")
            # Treat WGS84≈NAD83 if datums are effectively the same; fall back otherwise.
            if "NAD83" not in geodetic_crs.name.upper():
                raise ValueError(
                    "Failed to project lon/lat into dataset datum; "
                    "unable to convert WGS84 coordinates."
                ) from geo_err
        else:
            lon_geo, lat_geo = geo_result

    projected_result, proj_err = _transform_point(
        geodetic_crs or WGS84,
        target_crs,
        lon_geo,
        lat_geo,
    )
    if projected_result is not None:
        return projected_result

    errors.append(
        f"{(geodetic_crs or WGS84).to_string()}→{target_crs.to_string()} failed: {proj_err}"
    )

    area = target_crs.area_of_use
    if area is not None:
        bounds = (
            f"west={area.west_lon_degree:.2f}, east={area.east_lon_degree:.2f}, "
            f"south={area.south_lat_degree:.2f}, north={area.north_lat_degree:.2f}"
        )
        msg = (
            "Failed to project lon/lat into dataset CRS; the point may lie outside the "
            f"supported area ({bounds})."
        )
    else:
        msg = f"Failed to project lon/lat into dataset CRS ({target_crs.to_string()})."

    if errors:
        msg = f"{msg} Attempts: {' | '.join(errors)}"
    raise ValueError(msg) from proj_err


def _load_precip_cube(da_precip: xr.DataArray) -> xr.DataArray:
    """Load the precipitation cube, converting units from mm to inches."""
    return (da_precip / 1000 * 39.3701).load()


def _animation_payload_from_cube(precip_cube: xr.DataArray) -> dict:
    """Extract frames and times from the precipitation cube for animation."""
    frames = precip_cube.values
    times = precip_cube["time"].values if "time" in precip_cube.coords else None
    return {"frames": frames, "times": times}


def _orient_cube_north_up(cube: xr.DataArray) -> xr.DataArray:
    """Ensure the cube is oriented with north up by checking the y-coordinate values."""
    y_dim = None
    for candidate in ("y", "lat", "latitude", "projection_y_coordinate"):
        if candidate in cube.dims:
            y_dim = candidate
            break
    if y_dim is None:
        return cube

    coord = cube.coords.get(y_dim)
    if coord is None or coord.ndim != 1:
        return cube

    values = np.asarray(coord.values)
    if values.size == 0 or not np.isfinite(values).any():
        return cube

    if values[0] < values[-1]:
        return cube

    return cube.isel({y_dim: slice(None, None, -1)})


def _format_time_labels(times, frame_count: int) -> list[str]:
    """Format time labels for each frame based on provided times."""
    labels = []
    times_arr = np.asarray(times) if times is not None else None
    for idx in range(frame_count):
        label = None
        if times_arr is not None and idx < times_arr.shape[0]:
            val = times_arr[idx]
            try:
                label = np.datetime_as_string(np.datetime64(val), unit="h")
            except Exception:
                try:
                    label = np.array(val).astype(str)
                except Exception:
                    label = None
        if label is None:
            label = f"Hour {idx}"
        labels.append(label)
    return labels


def _bounds_to_extent(bounds):
    """Convert bounds to extent [west, east, south, north]."""
    if not bounds:
        return None
    try:
        south = float(bounds[0][0])
        west = float(bounds[0][1])
        north = float(bounds[1][0])
        east = float(bounds[1][1])
        return [west, east, south, north]
    except Exception:
        return None


@st.cache_data(show_spinner=True)
def build_storm_animation(
    frames: np.ndarray, times: np.ndarray, bounds: list[tuple[float, float]]
) -> str | None:
    """Build a matplotlib animation from precipitation frames.

    Parameters
    ----------
    frames: np.ndarray
        3D array of precipitation frames (time, y, x).
    times: np.ndarray
        1D array of time values corresponding to frames.
    bounds: list[tuple[float, float]]
        Geographic bounds as [(south, west), (north, east)].
    Returns
    -------
    str | None
        HTML representation of the animation, or None if invalid data.
    """
    if frames is None:
        return None
    data = np.asarray(frames)
    if data.ndim != 3 or data.size == 0:
        return None
    data = np.where(data == 0, np.nan, data)
    if not np.isfinite(data).any():
        return None
    extent = _bounds_to_extent(bounds)
    vmin = float(np.nanmin(data))
    vmax = float(np.nanmax(data))
    labels = _format_time_labels(times, data.shape[0])
    fig, ax = plt.subplots(figsize=(7, 5))
    image = ax.imshow(
        data[0],
        cmap="Spectral_r",
        vmin=vmin,
        vmax=vmax,
        extent=extent,
        origin="lower",
    )
    ax.set_xlabel("Longitude" if extent else "X")
    ax.set_ylabel("Latitude" if extent else "Y")
    title = ax.set_title(labels[0])

    def update(idx):
        image.set_data(data[idx])
        if extent:
            image.set_extent(extent)
        title.set_text(labels[idx])
        return (image, title)

    anim = FuncAnimation(
        fig,
        update,
        frames=data.shape[0],
        interval=400,
        blit=False,
        repeat=True,
    )
    html_anim = anim.to_jshtml()
    plt.close(fig)
    return html_anim


def _render_overlay_rgba(
    overlays: list[tuple[gpd.GeoDataFrame, dict]] | None,
    extent: list[float] | None,
    shape: tuple[int, int],
) -> np.ndarray | None:
    """Render overlay GeoDataFrames to an RGBA array for compositing."""
    if not overlays:
        return None
    height, width = shape
    if height <= 0 or width <= 0:
        return None

    fig_w = max(width / 120, 1)
    fig_h = max(height / 120, 1)
    fig, ax = plt.subplots(
        figsize=(fig_w, fig_h),
        dpi=120,
        facecolor=(0, 0, 0, 0),
    )
    ax.set_axis_off()
    ax.set_position([0, 0, 1, 1])
    ax.set_facecolor((0, 0, 0, 0))
    if extent:
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])

    for overlay_gdf, style in overlays:
        if overlay_gdf is None or overlay_gdf.empty:
            continue
        try:
            overlay_gdf.plot(ax=ax, **style)
        except Exception:
            continue

    fig.canvas.draw()
    overlay_rgba = np.asarray(fig.canvas.buffer_rgba())
    plt.close(fig)
    if overlay_rgba.ndim != 3 or overlay_rgba.shape[2] != 4:
        return None
    if overlay_rgba.shape[0] != height or overlay_rgba.shape[1] != width:
        overlay_rgba = np.array(
            Image.fromarray(overlay_rgba).resize((width, height), Image.NEAREST)
        )
    return overlay_rgba


def _frame_to_png_data_url(
    frame: np.ndarray,
    norm: plt.Normalize,
    cmap: plt.Colormap,
    overlay_rgba: np.ndarray | None = None,
) -> str:
    """Convert a single precipitation frame to a PNG data URL, applying colormap and overlay."""
    masked = np.ma.masked_invalid(frame)  # Mask invalid values for transparency
    masked = np.flipud(masked)  # Flip vertically to match image coordinate system
    rgba = (cmap(norm(masked)) * 255).astype(
        np.uint8
    )  # Apply colormap and convert to RGBA
    rgba[..., 3] = np.where(
        np.isfinite(masked), rgba[..., 3], 0
    )  # Set alpha to 0 for invalid values

    base_img = Image.fromarray(rgba, mode="RGBA")  # Create base image from RGBA array
    if overlay_rgba is not None:
        overlay_img = Image.fromarray(
            overlay_rgba, mode="RGBA"
        )  # Create overlay image from RGBA array
        base_img = Image.alpha_composite(
            base_img, overlay_img
        )  # Composite overlay onto base image

    buffer = io.BytesIO()  # Save the final image to a bytes buffer in PNG format
    base_img.save(buffer, format="PNG")  # Save the image to the buffer
    encoded = base64.b64encode(buffer.getvalue()).decode(
        "ascii"
    )  # Encode the PNG bytes as a base64 string
    return f"data:image/png;base64,{encoded}"


def build_storm_animation_maplibre(
    frames: np.ndarray,
    times: np.ndarray,
    bounds: list[tuple[float, float]] | None,
    style_url: str | None = None,
    interval_ms: int = 250,
) -> str | None:
    """Build a MapLibre animation from precipitation frames.

    Parameters
    ----------
    frames: np.ndarray
            3D array of precipitation frames (time, y, x).
    times: np.ndarray
            1D array of time values corresponding to frames.
    bounds: list[tuple[float, float]] | None
            Geographic bounds as [(south, west), (north, east)].
    style_url: str | None
        MapLibre style URL for the basemap. If None, uses a lightweight
        inline style with an OSM raster layer.
    interval_ms: int
            Frame interval in milliseconds.
    Returns
    -------
    str | None
            HTML string with a MapLibre animation, or None if invalid data.
    """
    if frames is None:
        return None
    data = np.asarray(frames)
    if data.ndim != 3 or data.size == 0:
        return None
    data = np.where(data == 0, np.nan, data)
    if not np.isfinite(data).any():
        return None
    extent = _bounds_to_extent(bounds)
    if extent is None:
        return None
    west, east, south, north = extent
    center_lon = (west + east) / 2.0
    center_lat = (south + north) / 2.0
    coords = [
        [west, north],
        [east, north],
        [east, south],
        [west, south],
    ]
    vmin = float(np.nanmin(data))
    vmax = float(np.nanmax(data))
    labels = _format_time_labels(times, data.shape[0])
    labels_serializable = [str(label) for label in labels]

    # Prepare overlay geometries and styles if available in session state
    overlays: list[tuple[gpd.GeoDataFrame, dict]] = []
    if st.transpo is not None and not st.transpo.empty:
        overlays.append(
            (
                st.transpo,
                {
                    "facecolor": "none",
                    "edgecolor": "#ff0404",
                    "linewidth": 2,
                    "alpha": 0.9,
                    "zorder": 3,
                },
            )
        )
    if st.study_area is not None and not st.study_area.empty:
        overlays.append(
            (
                st.study_area,
                {
                    "facecolor": "none",
                    "edgecolor": "#162fbe",
                    "linewidth": 2.0,
                    "alpha": 0.8,
                    "zorder": 2,
                },
            )
        )
    if st.transposed_study_area is not None and not st.transposed_study_area.empty:
        overlays.append(
            (
                st.transposed_study_area,
                {
                    "facecolor": "none",
                    "edgecolor": "#32cd32",
                    "linewidth": 2.0,
                    "alpha": 0.8,
                    "zorder": 2,
                },
            )
        )

    overlay_rgba = _render_overlay_rgba(overlays, extent, data.shape[1:3])
    norm = plt.Normalize(vmin=vmin, vmax=vmax)
    cmap = plt.get_cmap("Spectral_r")

    # Encode frames to PNG data URLs in parallel using ThreadPoolExecutor
    frame_encoder = partial(
        _frame_to_png_data_url,
        norm=norm,
        cmap=cmap,
        overlay_rgba=overlay_rgba,
    )
    with ThreadPoolExecutor() as executor:
        frame_urls = list(executor.map(frame_encoder, data))

    map_id = f"maplibre-{uuid4().hex}"
    label_id = f"maplibre-label-{uuid4().hex}"
    error_id = f"maplibre-error-{uuid4().hex}"
    fit_bounds = json.dumps([[west, south], [east, north]])
    inline_style = {
        "version": 8,
        "sources": {
            "osm": {
                "type": "raster",
                "tiles": ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
                "tileSize": 256,
                "attribution": "© OpenStreetMap contributors",
            }
        },
        "layers": [
            {
                "id": "background",
                "type": "background",
                "paint": {"background-color": "#dde"},
            },
            {"id": "osm", "type": "raster", "source": "osm"},
        ],
    }
    html = f"""
        <div style=\"width: 100%;\">
            <div id=\"{map_id}\" style=\"height: 500px; width: 100%;\"></div>
            <div id=\"{label_id}\" style=\"padding: 6px 10px; font-weight: 600;\"></div>
            <div id=\"{error_id}\" style=\"padding: 6px 10px; color: #b00020; font-weight: 600;\"></div>
        </div>
        <link
            href=\"https://unpkg.com/maplibre-gl@5.17.0/dist/maplibre-gl.css\"
            rel=\"stylesheet\"
        />
        <script src=\"https://unpkg.com/maplibre-gl@5.17.0/dist/maplibre-gl.js\"></script>
        <script>
            const frames = {json.dumps(frame_urls)};
            const labels = {json.dumps(labels_serializable)};
            const coords = {json.dumps(coords)};
            const inlineStyle = {json.dumps(inline_style)};
            const errorBox = document.getElementById("{error_id}");
            if (typeof maplibregl === "undefined") {{
                if (errorBox) {{
                    errorBox.textContent = "MapLibre failed to load. Check network access to unpkg.com.";
                }}
            }} else {{
                const map = new maplibregl.Map({{
                    container: "{map_id}",
                    style: {json.dumps(style_url)} || inlineStyle,
                    center: [{center_lon}, {center_lat}],
                    zoom: 5,
                    minZoom: 3,
                    maxZoom: 9
                }});
                map.addControl(new maplibregl.NavigationControl(), "top-right");
                let currentFrame = 0;
                map.on("error", (e) => {{
                    if (errorBox) {{
                        errorBox.textContent = "Map error: " + (e?.error?.message || "Unknown error");
                    }}
                }});
                map.on("load", () => {{
                    map.addSource("storm", {{
                        type: "image",
                        url: frames[0],
                        coordinates: coords
                    }});
                    map.addLayer({{
                        id: "storm-layer",
                        type: "raster",
                        source: "storm",
                        paint: {{ "raster-fade-duration": 0, "raster-opacity": 1.0 }}
                    }});
                    map.fitBounds({fit_bounds}, {{ padding: 20, duration: 0 }});
                    const label = document.getElementById("{label_id}");
                    if (label) {{ label.textContent = labels[0] || ""; }}
                    setInterval(() => {{
                        currentFrame = (currentFrame + 1) % frames.length;
                        const source = map.getSource("storm");
                        if (source) {{
                            source.updateImage({{ url: frames[currentFrame] }});
                        }}
                        if (label) {{ label.textContent = labels[currentFrame] || ""; }}
                    }}, {interval_ms});
                }});
            }}
        </script>
        """
    st.session_state["storm_animation_payload"] = None
    return html
