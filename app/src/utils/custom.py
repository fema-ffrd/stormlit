# standard imports
import re
import streamlit as st
import logging
from typing import TYPE_CHECKING, Callable, List, Optional

# third party imports
from streamlit.errors import StreamlitDuplicateElementKey

# module imports
from pages.hms_results import FeatureType
from utils.mapping import focus_feature

if TYPE_CHECKING:
    from streamlit.delta_generator import DeltaGenerator


def stylable_container(key: str, css_styles: str | list[str]) -> "DeltaGenerator":
    """
    Insert a container into your app which you can style using CSS.
    This is useful to style specific elements in your app.

    This is taken from the streamlit-extras package here:
    https://github.com/arnaudmiribel/streamlit-extras/blob/main/src/streamlit_extras/stylable_container/__init__.py

    Args:
        key (str): The key associated with this container. This needs to be unique since all styles will be
            applied to the container with this key.
        css_styles (str | List[str]): The CSS styles to apply to the container elements.
            This can be a single CSS block or a list of CSS blocks.

    Returns:
        DeltaGenerator: A container object. Elements can be added to this container using either the 'with'
            notation or by calling methods directly on the returned object.
    """

    class_name = re.sub(r"[^a-zA-Z0-9_-]", "-", key.strip())
    class_name = f"st-key-{class_name}"

    if isinstance(css_styles, str):
        css_styles = [css_styles]

    # Remove unneeded spacing that is added by the html:
    css_styles.append("""> div:first-child {margin-bottom: -1rem;}""")

    style_text = "<style>\n"

    for style in css_styles:
        style_text += f""".st-key-{class_name} {style}"""

    style_text += "</style>\n"

    container = st.container(key=class_name)
    container.html(style_text)
    return container


def map_popover(
    label: str,
    items: List[dict],
    get_item_label: Callable,
    get_item_id: Callable,
    color: str = "#f0f0f0",
    callback: Optional[Callable] = None,
    feature_type: Optional[FeatureType] = None,
    download_url: Optional[str] = None,
    image_path: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
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
    download_url: Optional[str]
        A URL to download data related to the items
    image_path: Optional[str]
        A path to an image to display in the popover
    Returns
    -------
    None

    """
    with stylable_container(
        key=f"popover_container_{label}",
        css_styles=f"""
            button {{
                background-color: {color};
                color: black;
                color: black;
                border-radius: 5px;
                white-space: nowrap;
            }}
        """,
    ):
        with st.popover(label, use_container_width=True):
            if image_path:
                st.image(image_path, use_container_width=False, width=200)
            st.markdown(f"#### {label}")
            if download_url:
                st.markdown(f"⬇️ [Download Data]({download_url})")
            if len(items) == 0:
                st.write(
                    "Select a feature from the map or model from the dropdown to generate selections"
                )
            for idx, item in enumerate(items):
                item_label = get_item_label(item)
                item_id = get_item_id(item)
                current_feature_id = st.session_state.get(
                    "single_event_focus_feature_id"
                )
                if item_id == current_feature_id and item_id is not None:
                    item_label += " ✅"
                button_key = f"btn_{label}_{item_id}_{idx}"

                if label != "🌧️ Storms":
                    try:
                        st.button(
                            label=item_label,
                            key=button_key,
                            on_click=focus_feature,
                            args=(item, item_id, item_label, feature_type),
                        )
                    except StreamlitDuplicateElementKey as e:
                        logger.warning(
                            f"Duplicate button key detected ({button_key}): {e}.",
                        )
                        st.button(
                            label=item_label,
                            key=f"{button_key}_DUPE",
                            on_click=focus_feature,
                            args=(item, item_id, item_label, feature_type),
                            disabled=True,
                        )
    st.map_output = None


def about_popover(color: str = "white"):
    """
    Render the styled About popover section.
    """
    with stylable_container(
        key="popover_container_about",
        css_styles=f"""
            button {{
                background-color: {color};
                color: black;
                border-radius: 5px;
                white-space: nowrap;
            }}
        """,
    ):
        with st.popover("READ ME ℹ️", use_container_width=True):
            st.markdown(
                """
            1. Select a pilot study to initialize the dataset.
            2. Select items from the map or dropdown.
            3. Turn map layers on and off using the layer toggle in the top right corner of the map.
            4. If selecting a model object, also select the event type and event ID:
            - **Single Event**: View deterministic results for a specific event.
                - Calibration events are historic simulations.
                - Stochastic events are synthetically generated.
            - **Multi Event**: View probabilistic results across an ensemble of stochastic events.
            5. After making a selection, statistics and analytics for that selection will be displayed to the right of the map.
            6. To reset selections, click the "Reset Selections" button located in the upper corner of the page
                """
            )
