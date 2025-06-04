# module imports
from components.layout import render_footer
from utils.session import init_session_state
from utils.stac_data import (
    init_pilot,
    define_gage_data,
    define_dam_data,
    get_stac_img,
    get_stac_meta,
    get_ref_line_ts,
    get_ref_pt_ts,
)
from utils.functions import get_map_pos, prep_fmap, plot_ts_dual_y_axis

# standard imports
import os
import streamlit as st
from streamlit.errors import StreamlitDuplicateElementKey
from dotenv import load_dotenv
from streamlit_folium import st_folium
from typing import Callable, List, Optional
from urllib.parse import urljoin
from enum import Enum
import logging
from shapely import Geometry

currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
assetsDir = os.path.abspath(os.path.join(srcDir, "assets"))  # go up one level to src
load_dotenv()

logger = logging.getLogger(__name__)


class FeatureType(Enum):
    BASIN = "Basin"
    GAGE = "Gage"
    DAM = "Dam"
    REFERENCE_LINE = "Reference Line"
    REFERENCE_POINT = "Reference Point"


def map_popover(
    label: str,
    items: List[dict],
    get_item_label: Callable,
    get_item_id: Callable,
    callback: Optional[Callable] = None,
    feature_type: Optional[FeatureType] = None,
    download_url: Optional[str] = None,
):
    """
    Create a popover with buttons for each item in the button_data list.

    When clicked, each button will update the session state with the
    corresponding item's latitude and longitude, and zoom level.

    Parameters
    ----------
    label: str
        The label for the popover
    items: list
        A list of dictionaries containing the button data
    get_item_label: Callable
        A function that takes an item and returns the label for the button
    get_item_id: Callable
        A function that takes an item and returns the ID for the button
    callback: Optional[Callable]
        A function to be called when the button is clicked. Accepts the item as an argument.
    feature_type: Optional[FeatureType]
        The type of feature (Basin, Gage, Dam, Reference Line, Reference Point)

    Returns
    -------
    None
    """
    with st.popover(label):
        st.markdown(f"#### {label}")
        if download_url:
            st.markdown(f"⬇️ [Download Data]({download_url})")
        for item in items:

            def _on_click(
                _item: dict, _item_id: str, _item_label: str, _feature_type: FeatureType
            ):
                logger.info("Item selected: %s", _item)
                geom: Optional[Geometry] = _item.get("geometry")
                if geom:
                    bounds = geom.bounds
                    bbox = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
                else:
                    bbox = None
                st.session_state.update(
                    {
                        "single_event_focus_feature_label": _item_label,
                        "single_event_focus_feature_id": _item_id,
                        "single_event_focus_lat": _item.get("lat"),
                        "single_event_focus_lon": _item.get("lon"),
                        # TODO: Add logic to determine zoom level based on item extent
                        "single_event_focus_zoom": 12,
                        "single_event_focus_bounding_box": bbox,
                        "single_event_focus_feature_type": _feature_type.value,
                    }
                )
                callback(item) if callback else None

            item_label = get_item_label(item)
            item_id = get_item_id(item)
            current_feature_id = st.session_state.get("single_event_focus_feature_id")
            if item_id == current_feature_id and item_id is not None:
                item_label += " ✅"
            button_key = f"btn_{item_id}"
            try:
                st.button(
                    label=item_label,
                    key=button_key,
                    on_click=_on_click,
                    args=(item, item_id, item_label, feature_type),
                )
            except StreamlitDuplicateElementKey as e:
                logger.warning(
                    f"Duplicate button key detected ({button_key}): {e}.",
                )
                st.button(
                    label=item_label,
                    key=f"{button_key}_DUPE",
                    on_click=_on_click,
                    args=(item, item_id, item_label, feature_type),
                    disabled=True,
                )


def single_event():
    st.set_page_config(page_title="stormlit", page_icon=":rain_cloud:", layout="wide")
    if "session_id" not in st.session_state:
        init_session_state()

    st.title("Single Event View")

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

    # Popovers for items on the map
    col_basins, col_dams, col_gages, col_ref_lines, col_ref_points = st.columns(5)
    with col_basins:
        map_popover(
            "🔵 Basins",
            st.basins.to_dict("records"),
            lambda basin: f"{basin['NAME']} ({basin['HUC8']})",
            get_item_id=lambda basin: basin["HUC8"],
            feature_type=FeatureType.BASIN,
            download_url=st.pilot_layers["Basins"],
        )
    with col_dams:
        map_popover(
            "🟥 Dams",
            st.dams.to_dict("records"),
            lambda dam: dam["id"],
            get_item_id=lambda dam: dam["id"],
            feature_type=FeatureType.DAM,
            download_url=st.pilot_layers["Dams"],
        )
    with col_gages:
        map_popover(
            "🟩 Gages",
            st.gages.to_dict("records"),
            lambda gage: gage["site_no"],
            get_item_id=lambda gage: gage["site_no"],
            feature_type=FeatureType.GAGE,
            download_url=st.pilot_layers["Gages"],
        )
    with col_ref_lines:
        map_popover(
            "🔷 Reference Lines",
            st.ref_lines.to_dict("records"),
            lambda ref_line: ref_line["id"],
            get_item_id=lambda ref_line: ref_line["id"],
            feature_type=FeatureType.REFERENCE_LINE,
            download_url=st.pilot_layers["Reference Lines"],
        )
    with col_ref_points:
        map_popover(
            "🟦 Reference Points",
            st.ref_points.to_dict("records"),
            lambda ref_point: ref_point["id"],
            get_item_id=lambda ref_point: ref_point["id"],
            feature_type=FeatureType.REFERENCE_POINT,
            download_url=st.pilot_layers["Reference Points"],
        )

    map_col, info_col = st.columns(2)

    # Map Position
    if st.session_state["single_event_focus_feature_label"]:
        c_lat = st.session_state["single_event_focus_lat"]
        c_lon = st.session_state["single_event_focus_lon"]
        zoom = st.session_state["single_event_focus_zoom"]
    # Default map position
    else:
        c_lat, c_lon, zoom = get_map_pos(
            "Study Area",
            None,
        )

    feature_type = st.session_state.get("single_event_focus_feature_type")
    if feature_type is not None:
        feature_type = FeatureType(feature_type)

    with map_col:
        with st.spinner("Loading Map..."):
            st.fmap = prep_fmap(
                list(st.pilot_layers.keys()),
                st.session_state["sel_cog_layer"],
                st.session_state["sel_cmap"],
            )
            # Fit the map to the bounding box of a selected polygon or line feature
            bbox = st.session_state.get("single_event_focus_bounding_box")
            if bbox and feature_type in [FeatureType.BASIN, FeatureType.REFERENCE_LINE]:
                st.fmap.fit_bounds(bbox)
                st.map_output = st_folium(
                    st.fmap,
                    height=500,
                    use_container_width=True,
                )
            else:
                st.map_output = st_folium(
                    st.fmap,
                    center=[c_lat, c_lon],
                    zoom=zoom,
                    height=500,
                    use_container_width=True,
                )

    with info_col:
        feature_label = st.session_state.get("single_event_focus_feature_label")
        feature_id = st.session_state.get("single_event_focus_feature_id")

        if feature_type == FeatureType.BASIN:
            info_col.markdown(f"### Basin: {feature_label}")
            info_col.markdown("Let's put more info here.")

        elif feature_type == FeatureType.DAM:
            info_col.markdown(f"### Dam: {feature_label}")
            dam_data = define_dam_data(feature_id)
            dam_meta_url = dam_data["Metadata"]
            dam_meta_status_ok, dam_meta = get_stac_meta(dam_meta_url)
            if dam_meta_status_ok:
                dam_stac_viewer_url = (
                    f"{st.session_state['stac_browser_url']}/#/external/{dam_meta_url}"
                )
                st.markdown(
                    f"🌐 [STAC Metadata for Dam {feature_id}]({dam_stac_viewer_url})"
                )

                st.markdown("#### Documentation")
                for asset_name, asset in dam_meta["assets"].items():
                    roles = asset.get("roles", [])
                    asset_href = asset.get("href")
                    asset_url = urljoin(dam_meta_url, asset_href)
                    if "document" in roles:
                        st.markdown(f"📄 [{asset_name}]({asset_url})")
                    elif "spreadsheet" in roles:
                        st.markdown(f"📊 [{asset_name}]({asset_url})")

        elif feature_type == FeatureType.GAGE:
            info_col.markdown(f"### Gage: `{feature_label}`")
            gage_data = define_gage_data(feature_id)
            gage_meta_url = gage_data["Metadata"]
            gage_meta_status_ok, gage_meta = get_stac_meta(gage_meta_url)
            if gage_meta_status_ok:
                gage_stac_viewer_url = (
                    f"{st.session_state['stac_browser_url']}/#/external/{gage_meta_url}"
                )
                gage_props = gage_meta.get("properties", {})
                st.markdown(f"""
                            * **Station Name:** {gage_props.get("station_nm")}
                            * **Site No:** `{gage_props.get("site_no")}`
                            * **HUC:** `{gage_props.get("huc_cd")}`
                            * **Drainage Area:** {gage_props.get("drain_area_va")}
                            """)
                st.markdown(
                    f"🌐 [STAC Metadata for Gage {feature_id}]({gage_stac_viewer_url})"
                )

            st.markdown("#### Gage Analytics")
            for plot_type, plot_url in gage_data.items():
                if plot_type != "Metadata":
                    st.markdown(f"##### {plot_type}")
                    plot_status_ok, plot_img = get_stac_img(plot_url)
                    if plot_status_ok:
                        st.image(plot_img, use_container_width=True)
                    else:
                        st.error(f"Error retrieving {plot_type} image.")

        elif feature_type == FeatureType.REFERENCE_LINE:
            info_col.markdown(f"### Reference Line: `{feature_label}`")
            ref_line_ts = get_ref_line_ts(feature_id)
            plot_ts_dual_y_axis(
                ref_line_ts, "water_surface", "flow", info_col, title=feature_label
            )

        elif feature_type == FeatureType.REFERENCE_POINT:
            info_col.markdown(f"### Reference Point: `{feature_label}`")
            ref_pt_ts = get_ref_pt_ts(feature_id)
            plot_ts_dual_y_axis(
                ref_pt_ts, "water_surface", "velocity", info_col, title=feature_label
            )

        else:
            st.markdown("### Single Event View")
            st.markdown(
                "Select a Basin, Gage, Dam, Reference Line, or Reference Point for details."
            )

    # Session state
    with st.expander("Session State"):
        st.write(st.session_state)

    # Footer
    render_footer()


if __name__ == "__main__":
    single_event()
