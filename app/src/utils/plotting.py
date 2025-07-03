import streamlit as st
import pandas as pd
from plotly import express as px
import plotly.graph_objects as go
from typing import Optional


def plot_ts(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    var1: str,
    var2: str,
    dual_y_axis: bool,
    title: Optional[str] = None,
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
    title : Optional[str]
        The title of the plot. If None, a default title will be used.
    """
    # Check if the DataFrames are empty
    if df1.empty and df2.empty:
        st.warning("No data available for the selected variables in either dataset.")
        return

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
            title=title if title else f"Time Series Plot of {var1} and {var2}",
            xaxis_title="Time",
            yaxis=dict(
                title=var1,
                showgrid=False,
                zeroline=True,
            ),
            yaxis2=dict(
                title=var2,
                overlaying="y",
                side="right",
                showgrid=False,
                zeroline=True,
            ),
            legend=dict(x=0.75, y=1, traceorder="normal"),
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
    df: pd.DataFrame,
):
    """Function for plotting Discharge Frequency Plot.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing the AEP, Return Period, and Peak Flow data.
    """
    # Check if the DataFrames are empty
    if df.empty:
        st.warning("No data available for the selected variables in the dataset.")
        return

    fig = go.Figure()

    # Add trace for AEP vs Peak Flow
    fig.add_trace(
        go.Scattergl(
            x=df["aep"],
            y=df["peak_flow"],
            mode="markers",
            name="Discharge (cfs)",
            marker=dict(color="white"),
            yaxis="y1",
            xaxis="x1",
            hoverinfo="skip",
        )
    )
    # Add trace for Return Period vs Peak Flow
    fig.add_trace(
        go.Scattergl(
            x=df["return_period"],
            y=df["peak_flow"],
            mode="markers",
            name="Discharge (cfs)",
            marker=dict(color="red"),
            yaxis="y2",
            xaxis="x2",
            text=[
                f"Return Period: {rp}<br>Peak Flow: {peak_flow}<br>AEP: {aep}<br>Block Group: {block}<br>Event ID: {event_id}<br>Storm ID: {storm_id}"
                for rp, peak_flow, aep, block, event_id, storm_id in zip(
                    df["return_period"],
                    df["peak_flow"],
                    df["aep"],
                    df["block_group"],
                    df["event_id"],
                    df["storm_id"],
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
            title="Discharge (cfs)",
            type="log",
        ),
        yaxis2=dict(
            title="Discharge (cfs)",
            type="log",
            overlaying="y1",
            side="left",
        ),
        title="Block Maximum Discharge Frequency Plot",
    )
    # Remove the legend
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
