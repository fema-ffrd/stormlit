import re
import folium
import uuid
import streamlit as st
from datetime import datetime


def create_st_button(link_text: str, link_url: str, hover_color="#e78ac3", st_col=None):
    """
    Create a Streamlit button with a hover effect

    Parameters
    ----------
    link_text: str
        The text to display on the button
    link_url: str
        The URL to open when the button is clicked
    hover_color: str
        The color to change to when the button is hovered over
    st_col: streamlit.delta_generator.DeltaGenerator
        The streamlit column to display the button in
    """

    button_uuid = str(uuid.uuid4()).replace("-", "")
    button_id = re.sub("\d+", "", button_uuid)

    button_css = f"""
        <style>
            #{button_id} {{
                background-color: rgb(255, 255, 255);
                color: rgb(38, 39, 48);
                padding: 0.25em 0.38em;
                position: relative;
                text-decoration: none;
                border-radius: 4px;
                border-width: 1px;
                border-style: solid;
                border-color: rgb(230, 234, 241);
                border-image: initial;

            }}
            #{button_id}:hover {{
                border-color: {hover_color};
                color: {hover_color};
            }}
            #{button_id}:active {{
                box-shadow: none;
                background-color: {hover_color};
                color: white;
                }}
        </style> """

    html_str = f'<a href="{link_url}" target="_blank" id="{button_id}";>{link_text}</a><br></br>'

    if st_col is None:
        st.markdown(button_css + html_str, unsafe_allow_html=True)
    else:
        st_col.markdown(button_css + html_str, unsafe_allow_html=True)


@st.cache_data
def prep_fmap(sel_layers: list,
              basemap: str = "OpenStreetMap"):
    """
    Prep a folium map object given a geojson with a specificed basemap

    Parameters
    ----------
    sel_layers: dict
        A list of selected map layers to plot
    basemap: str
        Basemap to use for the map.
        Options are "OpenStreetMap", "ESRI Satellite", and "Google Satellite"

    Returns
    -------
    folium.Map
        Folium map object
    folium.FeatureGroup
        Folium feature group object
    """
    time1 = datetime.now()
    df_dict = {}
    for layer in sel_layers:
        if layer == "Subbasins" and st.subbasins is not None:
            df_dict["Subbasins"] = st.subbasins
        elif layer == "Reachs" and st.reaches is not None:
            df_dict["Reachs"] = st.reaches
        elif layer == "Junctions" and st.junctions is not None:
            df_dict["Junctions"] = st.junctions
        elif layer == "Reservoirs" and st.reservoirs is not None:
            df_dict["Reservoirs"] = st.reservoirs

    # Get the centroid from the first GeoDataFrame in the dictionary
    c_df = df_dict[sel_layers[0]]
    c_lat, c_lon = c_df["lat"].mean(), c_df["lon"].mean()
    # Create a folium map centered at the mean latitude and longitude
    m = folium.Map(location=[c_lat, c_lon], zoom_start=10)
    # Specify the basemap
    if basemap == "ESRI Satellite":
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri",
            name="Esri Satellite",
            overlay=False,
            control=True,
        ).add_to(m)
    elif basemap == "Google Satellite":
        folium.TileLayer(
            tiles="http://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
            attr="Google",
            name="Google Satellite",
            overlay=False,
            control=True,
        ).add_to(m)
    else:
        folium.TileLayer("openstreetmap").add_to(m)
    # Create a feature group for the map data
    fg = folium.FeatureGroup(name="Map Data")
    idx = 0
    for key, df in df_dict.items():
        df["layer"] = key
        # Add the GeoDataFrame geometry to the map
        if "LineString" in df.geometry.geom_type.unique():
            m_color = "red"
        else:
            m_color = "blue"
        fg.add_child(folium.GeoJson(df,
                                    name=sel_layers[idx],
                                    zoom_on_click=True,
                                    color=m_color,
                                    tooltip=folium.GeoJsonTooltip(fields=["layer", "id"])))
        idx += 1
    time2 = datetime.now()
    print(f"Time to create map: {time2 - time1}")
    return m, fg


def get_map_sel(map_output: str):
    """
    Return the selection from the map as a filtered GeoDataFrame

    Parameters
    ----------
    map_output: str
        The map output from the folium map

    Returns
    -------
    pd.DataFrame
        A filtered GeoDataFrame based on the map selection
    """
    tooltip_text = map_output["last_object_clicked_tooltip"]
    # Split the tooltip multi line string into objects
    items = tooltip_text.split("\n")
    items = [item.replace(" ", "") for item in items if len(item.replace(" ", "")) > 0]
    layer_col = items[0] # layer column
    layer_val = items[1] # layer value
    id_col = items[2] # id column
    id_val = items[3] # id value
    if layer_val == "Subbasins" and st.subbasins is not None:
        df = st.subbasins
    elif layer_val == "Reachs" and st.reaches is not None:
        df = st.reaches
    elif layer_val == "Junctions" and st.junctions is not None:
        df = st.junctions
    elif layer_val == "Reservoirs" and st.reservoirs is not None:
        df = st.reservoirs
    else:
        raise ValueError(f"Invalid map layer {layer_col} with value {layer_val} and column {id_col} with value {id_val}")
    # filter based on the map selection
    df = df[df["id"] == id_val]
    return df