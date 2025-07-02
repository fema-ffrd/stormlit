# standard imports
import re
import streamlit as st
from typing import TYPE_CHECKING

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
