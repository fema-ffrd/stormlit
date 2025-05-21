import streamlit as st
import streamlit.components.v1 as components
import uuid
from typing import Optional, Callable

def clickable_link(text: str, key: Optional[str] = None, on_click: Optional[Callable[[], None]] = None) -> bool:
    """
    Displays a clickable link in Streamlit that looks like an <a> tag and triggers
    a callback-style Python function when clicked.

    Args:
        text: The text to display as the link.
        key: Optional unique key to track click state.
        on_click: Optional function to call if the link is clicked.

    Returns:
        True if the link was clicked on this run.
    """
    key = key or str(uuid.uuid4()).replace("-", "")
    link_id = f"clickable-link-{key}"
    query_param = f"link_clicked_{key}"

    # Detect if the link was clicked via query param
    clicked = query_param in st.query_params

    if clicked:
        # Clear query param so it doesn't persist
        st.query_params.pop(query_param, None)
        st.experimental_set_query_params(**st.query_params)

    # Render the clickable link and JS handler
    components.html(f"""
        <a href="#" id="{link_id}" style="color: #1a73e8; text-decoration: underline; cursor: pointer;">
            {text}
        </a>
        <script>
            const link = window.parent.document.getElementById("{link_id}");
            if (link) {{
                link.addEventListener("click", function(e) {{
                    e.preventDefault();
                    const url = new URL(window.location.href);
                    url.searchParams.set("{query_param}", "1");
                    window.location.href = url.toString();
                }});
            }}
        </script>
    """, height=30)

    if clicked and on_click:
        on_click()

    return clicked
