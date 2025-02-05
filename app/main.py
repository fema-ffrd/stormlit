# standard imports
import warnings
import streamlit as st
from dotenv import load_dotenv

# custom imports
from src.pages.home_page import home_page
from src.pages.view_map import view_map
from src.pages.view_gages import view_gages
from src.pages.view_storms import view_storms

warnings.simplefilter(action="ignore", category=FutureWarning)
load_dotenv()


class MultiApp:
    def __init__(self):
        self.apps = []

    def add_app(self, title, func):
        self.apps.append({"title": title, "function": func})

    def run(self):
        st.set_page_config(
            page_title="stormlit", page_icon=":rain_cloud:", layout="wide"
        )

        st.sidebar.markdown("## Main Menu")
        app = st.sidebar.selectbox(
            "Select Page", self.apps, format_func=lambda app: app["title"]
        )
        st.sidebar.markdown("---")
        app["function"]()


app = MultiApp()

app.add_app("Home Page", home_page)
app.add_app("View Map", view_map)

app.run()
