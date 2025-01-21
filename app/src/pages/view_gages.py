# standard imports
import os
import sys
import plotly.graph_objects as go
import streamlit as st
from scipy.stats import norm
from components.tables import stylized_table
from dotenv import load_dotenv

# global variables
GAGES_DATA = "s3://kanawha-pilot/stac/Kanawha-0505/data-summary/gages.pq"
currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
sys.path.append(srcDir)
load_dotenv()

# custom imports
from utils.stac_data import init_gage_data
from utils.session import init_session_state
from components.layout import render_footer
from configs.settings import LOG_LEVEL


def view_gages():
    if "session_id" not in st.session_state:
        init_session_state()

    st.stac_url = os.getenv("STAC_API_URL")

    st.session_state.log_level = LOG_LEVEL

    if st.session_state["init_gage_data"] is False:
        st.write("Initializing datasets...")
        init_gage_data(GAGES_DATA)
        st.session_state["init_gage_data"] = True
        st.balloons()
        st.success("Complete! Gage data is now ready for exploration.")

    st.markdown("## Gage Viewer")

    df = st.gages

    col1, col2 = st.columns(2)

    with col1:
        st.session_state["model_name"] = st.selectbox(
            "Search for results by Model", df["ras_model"].unique()
        )
        df = df[
            df["ras_model"].str.contains(
                st.session_state["model_name"], case=False, na=False
            )
        ]

        st.session_state["gage_id"] = st.selectbox(
            "Search for results by Gage", ["None", *df["gage"].unique()]
        )

        st.session_state["variable"] = st.selectbox(
            "Select Water Surface Elevation or Flow", ["Flow", "WSE"]
        )

        st.session_state["realization"] = st.multiselect(
            "Select Realization", df["realization"].unique()
        )

        if st.session_state["variable"] == "Flow":
            value, time, plot_label = "max_flow_value", "max_flow_time", "Flow (cfs)"
        else:
            value, time, plot_label = (
                "max_wse_value",
                "max_wse_time",
                "Water Surface Elevation(ft)",
            )

        if (
            st.session_state["gage_id"] != "None"
            and len(st.session_state["realization"]) > 0
        ):
            df = df[
                df["gage"].str.contains(
                    st.session_state["gage_id"], case=False, na=False
                )
            ]
            df = df[df["realization"].isin(st.session_state["realization"])]
            df["rank"] = df[value].rank(ascending=False)
            stylized_table(
                df[["ID", value, "rank", "Link"]].sort_values(by="rank", ascending=True)
            )

    with col2:
        realization_colors = {1: "red", 2: "blue", 3: "green", 4: "orange", 5: "purple"}
        fig = go.Figure()

        if (
            st.session_state["gage_id"] != "None"
            and len(st.session_state["realization"]) > 0
        ):
            for realization in df["realization"].unique():
                realization_df = df[df["realization"] == realization]
                realization_df = realization_df.sort_values(by=value, ascending=False)
                realization_df["rank"] = realization_df[value].rank(ascending=False)
                realization_df["weibull_position"] = realization_df["rank"] / (
                    len(realization_df) + 1
                )

                rank = realization_df["rank"].values.astype(int)
                pp = [i / (len(rank) + 1) for i in rank]
                z_scores = [norm.ppf(1 - p) for p in pp]

                fig.add_trace(
                    go.Scatter(
                        x=z_scores,
                        y=realization_df[value],
                        mode="markers",
                        name=f"Realization {realization}",
                        marker=dict(color=realization_colors.get(realization, "black")),
                        hovertext=realization_df["ID"],
                    )
                )

            fig.update_layout(
                title=st.session_state["gage_id"],
                xaxis_title="Z-Scores",
                yaxis_title=plot_label,
                yaxis_type="log",
            )

            st.plotly_chart(fig)

    render_footer()
