import plotly.express as px
import pandas as pd


def create_time_series_plot(df: pd.DataFrame):
    """
    Create a Plotly time series plot from a DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing the time series data with datetime index.
        Single column DataFrame with datetime index.

    Returns
    -------
    fig : plotly.graph_objects.Figure
        Plotly figure object.
    """
    target_col = df.columns[0]
    df["date"] = df.index
    df = df.reset_index(drop=True)
    # Create the Plotly figure
    fig = px.line(df, x="date", y=target_col, title="Gage Period of Record")
    return fig
