import streamlit as st
import pandas as pd
from plotly import express as px
import plotly.graph_objects as go
from typing import Optional

from utils.constants import (
    FLOW_LABEL,
)


def plot_ts(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    var1: str,
    var2: str,
    dual_y_axis: bool,
    plot_title: Optional[str] = None,
    y_axis01_title: Optional[str] = None,
    y_axis02_title: Optional[str] = None,
):
    """Function for plotting time series data from two DataFrames with dual y-axes.
    Each DataFrame should have:
    - 'time': datetime
    - var1: float (for df1)
    - var2: float (for df2)
    Parameters
    ----------
    df1 : pd.DataFrame
        The first DataFrame containing the time series data.
    df2 : pd.DataFrame
        The second DataFrame containing the time series data.
    var1 : str
        The first variable to plot.
    var2 : str
        The second variable to plot.
    dual_y_axis : bool
        Whether to plot the second variable on a secondary y-axis.
    plot_title : Optional[str]
        The title of the plot. If None, a default title will be used.
    y_axis01_title : Optional[str]
        The title for the primary y-axis.
    y_axis02_title : Optional[str]
        The title for the secondary y-axis (if dual_y_axis is True).
    """
    # Check if the DataFrames are empty
    if df1.empty and df2.empty:
        st.warning("No data available for the selected variables in either dataset.")
        return

    if "time" in df1.columns and var1 in df1.columns:
        df1 = df1[["time", var1]].dropna()

    if "time" in df2.columns and var2 in df2.columns:
        df2 = df2[["time", var2]].dropna()

    fig = go.Figure()

    if not dual_y_axis:
        # Add traces for the first DataFrame
        if not df1.empty:
            fig.add_trace(
                go.Scatter(
                    x=df1["time"],
                    y=df1[var1],
                    mode="lines",
                    name=f"{var1}",
                    line=dict(color="red"),
                    yaxis="y1",
                )
            )

        # Add traces for the second DataFrame
        if not df2.empty:
            fig.add_trace(
                go.Scatter(
                    x=df2["time"],
                    y=df2[var2],
                    mode="lines",
                    name=f"{var2}",
                    line=dict(color="blue"),
                    yaxis="y1",
                )
            )
        # Update layout for single y-axis
        fig.update_layout(
            xaxis_title="Time",
            yaxis_title=y_axis01_title,
            showlegend=True,
        )
    else:
        # Add traces for the first DataFrame
        if not df1.empty:
            fig.add_trace(
                go.Scatter(
                    x=df1["time"],
                    y=df1[var1],
                    mode="lines",
                    name=f"{var1}",
                    line=dict(color="red"),
                    yaxis="y1",
                )
            )

        # Add traces for the second DataFrame
        if not df2.empty:
            fig.add_trace(
                go.Scatter(
                    x=df2["time"],
                    y=df2[var2],
                    mode="lines",
                    name=f"{var2}",
                    line=dict(color="blue"),
                    yaxis="y2",
                )
            )
        # Update layout for dual y-axes
        fig.update_layout(
            title=plot_title
            if plot_title
            else f"Time Series Plot of {var1} and {var2}",
            xaxis_title="Time",
            yaxis=dict(
                title=var1 if y_axis01_title is None else y_axis02_title,
                showgrid=False,
                side="left",
                zeroline=True,
            ),
            yaxis2=dict(
                title=var2 if y_axis02_title is None else y_axis01_title,
                overlaying="y",
                side="right",
                showgrid=False,
                zeroline=True,
            ),
            legend=dict(x=0.75, y=1, traceorder="normal"),
        )
    # Add crosshair spikes
    fig.update_xaxes(
        showspikes=True, spikemode="across", spikesnap="cursor", spikethickness=1
    )
    fig.update_yaxes(
        showspikes=True, spikemode="across", spikesnap="cursor", spikethickness=1
    )

    st.plotly_chart(fig)


def plot_hist(df: pd.DataFrame, x_col: str, y_col: str, nbins: int):
    """
    Function for plotting histogram data.

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame containing the histogram data.
    x_col : str
        The column name for the x-axis values.
    y_col : str
        The column name for the y-axis values.
    nbins : int
        The number of bins for the histogram.
    """
    # Check if the DataFrame is empty
    if df.empty:
        st.warning("No data available for the selected variable.")
        return
    fig = px.histogram(
        df,
        nbins=nbins,
        x=x_col,
        y=y_col,
        title="Histogram of Raster Values",
        labels={x_col: "COG Value", y_col: "Count"},
    )
    fig.update_traces(marker_color="blue")
    fig.update_layout(
        xaxis_title=x_col,
        yaxis_title=y_col,
        showlegend=True,
    )
    return fig


def plot_flow_aep(
    multi_event_ams_df: pd.DataFrame,
    gage_ams_df: Optional[pd.DataFrame] = None,
):
    """Function for plotting Discharge Frequency Plot.

    Parameters
    ----------
    multi_event_ams_df : pd.DataFrame
        DataFrame containing the multi event AEP, Return Period, and Peak Flow data.
        - "aep": float
        - "return_period": float
        - "peak_flow": float
    gage_ams_df : Optional[pd.DataFrame]
        DataFrame containing the gage AEP, Return Period, and Peak Flow data.
        - "aep": float
        - "return_period": float
        - "peak_flow": float
    """
    # Check if the DataFrames are empty
    if multi_event_ams_df.empty:
        st.warning("No data available for the selected variables in the dataset.")
        return

    fig = go.Figure()

    # Add trace for AEP vs Peak Flow
    fig.add_trace(
        go.Scattergl(
            x=multi_event_ams_df["aep"],
            y=multi_event_ams_df["peak_flow"],
            mode="markers",
            name=None,
            marker=dict(color="white"),
            yaxis="y1",
            xaxis="x1",
            hoverinfo="skip",
            showlegend=False,
        )
    )
    # Add trace for Return Period vs Peak Flow
    fig.add_trace(
        go.Scattergl(
            x=multi_event_ams_df["return_period"],
            y=multi_event_ams_df["peak_flow"],
            mode="markers",
            name="Modeled",
            marker=dict(color="red"),
            yaxis="y2",
            xaxis="x2",
            text=[
                f"Return Period: {rp:,.1f}<br>Peak Flow: {peak_flow:,.1f}<br>AEP: {aep:,.2e}<br>Block Group: {block:,}<br>Event ID: {event_id:,}<br>Storm ID: {storm_id}"
                for rp, peak_flow, aep, block, event_id, storm_id in zip(
                    multi_event_ams_df["return_period"],
                    multi_event_ams_df["peak_flow"],
                    multi_event_ams_df["aep"],
                    multi_event_ams_df["block_group"],
                    multi_event_ams_df["event_id"],
                    multi_event_ams_df["storm_id"],
                )
            ],
        )
    )
    # Add trace for Gage AEP vs Peak Flow if provided
    if gage_ams_df is not None and not gage_ams_df.empty:
        fig.add_trace(
            go.Scattergl(
                x=gage_ams_df["aep"],
                y=gage_ams_df["peak_flow"],
                mode="markers",
                name=None,
                marker=dict(color="white"),
                yaxis="y1",
                xaxis="x1",
                hoverinfo="skip",
                showlegend=False,
            )
        )
        # Add trace for Gage Return Period vs Peak Flow
        fig.add_trace(
            go.Scattergl(
                x=gage_ams_df["return_period"],
                y=gage_ams_df["peak_flow"],
                mode="markers",
                name="Observed",
                marker=dict(color="blue"),
                yaxis="y2",
                xaxis="x2",
                text=[
                    f"Gage ID: {gage_id}<br>Return Period: {rp:,.1f}<br>Peak Flow: {peak_flow:,.1f}<br>AEP: {aep:,.2e}<br>Storm ID: {peak_time}"
                    for gage_id, rp, peak_flow, aep, peak_time in zip(
                        gage_ams_df["gage_id"],
                        gage_ams_df["return_period"],
                        gage_ams_df["peak_flow"],
                        gage_ams_df["aep"],
                        gage_ams_df["peak_time"],
                    )
                ],
            )
        )

    # Update layout for dual y-axes
    fig.update_layout(
        xaxis=dict(
            title="AEP",
            autorange="reversed",
            type="log",
            showgrid=True,
        ),
        xaxis2=dict(
            title="Return Period (Years)",
            overlaying="x",
            side="top",
            type="log",
        ),
        yaxis1=dict(
            title=FLOW_LABEL,
            type="log",
        ),
        yaxis2=dict(
            title=FLOW_LABEL,
            type="log",
            overlaying="y1",
            side="left",
        ),
        title="Block Maximum Discharge Frequency Plot",
    )
    # place the legend at the bottom center horizontally
    fig.update_layout(
        legend=dict(
            x=0.5,
            y=-0.4,
            xanchor="center",
            yanchor="bottom",
            orientation="h",
            traceorder="normal",
        )
    )

    # Add crosshair spikes
    fig.update_xaxes(
        showspikes=True, spikemode="across", spikesnap="cursor", spikethickness=1
    )
    fig.update_yaxes(
        showspikes=True, spikemode="across", spikesnap="cursor", spikethickness=1
    )

    # Return point selection(s)
    plot_selection = st.plotly_chart(
        fig, use_container_width=True, on_select="rerun", selection_mode="points"
    )
    if len(plot_selection["selection"]["points"]) > 0:
        points_dict = {}
        selected_points = pd.DataFrame(plot_selection["selection"]["points"])
        for _, row in selected_points.iterrows():
            if "Gage ID" in row["text"].split("<br>")[0]:
                storm_id = row["text"].split("<br>")[4].split(": ")[1].replace(",", "")
                storm_id_dt = pd.to_datetime(
                    storm_id, format="%Y-%m-%d", errors="coerce"
                )
                if pd.notnull(storm_id_dt):
                    month_str = storm_id_dt.strftime("%b").lower()  # e.g., 'oct'
                    year_str = storm_id_dt.strftime("%Y")  # e.g., '2015'
                    storm_id_fmt = f"{month_str}{year_str}"  # e.g., 'oct2015'
                else:
                    storm_id_fmt = storm_id
                points_dict[storm_id_fmt] = {}
                points_dict[storm_id_fmt]["gage_id"] = (
                    row["text"].split("<br>")[0].split(": ")[1]
                )
                points_dict[storm_id_fmt]["return_period"] = float(row["x"])
                points_dict[storm_id_fmt]["peak_flow"] = float(row["y"])
                points_dict[storm_id_fmt]["aep"] = float(
                    row["text"].split("<br>")[1].split(": ")[1].replace(",", "")
                )
                points_dict[storm_id_fmt]["event_id"] = None
                points_dict[storm_id_fmt]["storm_id"] = storm_id_fmt
                points_dict[storm_id_fmt]["peak_time"] = storm_id
            else:
                block_group = (
                    row["text"].split("<br>")[3].split(": ")[1].replace(",", "")
                )
                points_dict[block_group] = {}
                points_dict[block_group]["return_period"] = float(row["x"])
                points_dict[block_group]["peak_flow"] = float(row["y"])
                points_dict[block_group]["aep"] = float(
                    row["text"].split("<br>")[2].split(": ")[1].replace(",", "")
                )
                points_dict[block_group]["event_id"] = (
                    row["text"].split("<br>")[4].split(": ")[1].replace(",", "")
                )
                points_dict[block_group]["storm_id"] = (
                    row["text"]
                    .split("<br>")[5]
                    .split(": ")[1]
                    .replace("-", "")
                    .replace(",", "")
                )
        return points_dict
    else:
        return None


def plot_multi_event_ts(df1: pd.DataFrame, df2: pd.DataFrame):
    """
    Create a multi-trace plot for time series data with multiple events.

    Parameters
    ----------
    df1 : pd.DataFrame
        DataFrame containing the multi-event time series data for flows.
        - "time": datetime
        - "hms_flow": float
        - "block_id": int
    df2 : pd.DataFrame
        DataFrame containing the multi-event time series data for baseflows.
        - "time": datetime
        - "hms_flow": float
        - "block_id": int

    Returns
    -------
    fig : plotly.graph_objects.Figure
    """
    # Check if the DataFrame is empty
    if df1.empty and df2.empty:
        st.warning("No data available for the selected variables in the dataset.")
        return

    # Create a figure
    fig = go.Figure()
    df1["plot_index"] = df1.index
    df2["plot_index"] = df2.index

    if not df1.empty:
        # Add traces for each hydrograph
        for block_id in df1["block_id"].unique():
            block_data = df1[df1["block_id"] == block_id]
            if "hms_flow" in block_data.columns:
                fig.add_trace(
                    go.Scatter(
                        x=block_data["plot_index"],
                        y=block_data["hms_flow"],
                        mode="lines",
                        name=f"Block {block_id}",
                        line=dict(width=1),
                    )
                )
            elif "obs_flow" in block_data.columns:
                fig.add_trace(
                    go.Scatter(
                        x=block_data["plot_index"],
                        y=block_data["obs_flow"],
                        mode="lines",
                        name=f"Observed {block_id}",
                        line=dict(width=1),
                    )
                )
            else:
                st.warning(
                    f"No data available for the selected variables in the dataset. {block_id}."
                )

    if not df2.empty:
        # Add traces for baseflows if available
        for block_id in df2["block_id"].unique():
            block_data = df2[df2["block_id"] == block_id]
            if "hms_flow" in block_data.columns:
                fig.add_trace(
                    go.Scatter(
                        x=block_data["plot_index"],
                        y=block_data["hms_flow"],
                        mode="lines",
                        name=f"Baseflow Block {block_id}",
                        line=dict(width=1, dash="dash"),
                    )
                )
            else:
                st.warning(
                    f"No data available for the selected variables in the dataset. {block_id}."
                )

    # Update layout
    fig.update_layout(
        title="Multi-Event Time Series Hydrographs",
        xaxis_title="Time (hours)",
        yaxis_title=FLOW_LABEL,
        legend=dict(x=0.75, y=1, traceorder="normal"),
    )
    # Add crosshair spikes
    fig.update_xaxes(
        showspikes=True, spikemode="across", spikesnap="cursor", spikethickness=1
    )
    fig.update_yaxes(
        showspikes=True, spikemode="across", spikesnap="cursor", spikethickness=1
    )
    # Set hovermode to unified
    st.plotly_chart(fig, use_container_width=True)
