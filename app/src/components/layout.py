import streamlit as st


def configure_page_settings(name: str):
    return st.set_page_config(page_title=name, layout="wide")


def render_footer():
    try:
        # Create the HTML content for the footer with right-aligned text
        footer_html = """
        <style>
        .footer {
            position: fixed;
            left: 0;
            bottom: 0;
            width: 100%;
            text-align: right;
            padding-right: 20px;
            padding-top: 5px;
            display: flex;
            justify-content: flex-end;
            align-items: center;
            background-color: inherit; /* Inherits the background color based on the theme */
        }
        @media (prefers-color-scheme: dark) {
            .footer {
                background-color: #333;
                color: #fff;
            }
        }
        @media (prefers-color-scheme: light) {
            .footer {
                background-color: #f1f1f1;
                color: #000;
            }
        }
        </style>
        <div class="footer">
            <p> FFRD Stac Client, © 2024 fema-ffrd  </p>
        </div>
        """

        # Render the footer with right-aligned text
        st.markdown(footer_html, unsafe_allow_html=True)

    except Exception as e:
        st.error(f"An error occurred: {e}")
