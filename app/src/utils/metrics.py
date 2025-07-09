# -*- coding: utf-8 -*-

# Imports #####################################################################
import streamlit as st
import pandas as pd
import numpy as np
from permetrics.regression import RegressionMetric

# Functions ###################################################################


def define_metrics():
    st.write(
        "R2: Coefficient of Determination. Strength of linear association between predicted and observed. However, it measures “precision” but no accuracy"
    )
    st.latex(
        r"""R^2 = 1 - \frac{\sum_{i=1}^{n}(y_i - \hat{y}_i)^2}{\sum_{i=1}^{n}(y_i - \bar{y})^2}"""
    )
    st.write(
        "NSE: Nash-Sutcliffe Efficiency. Model efficiency using squared residuals normalized by the variance of observations."
    )
    st.latex(
        r"""NSE = 1 - \frac{\sum_{i=1}^{n}(y_i - \hat{y}_i)^2}{\sum_{i=1}^{n}(y_i - \bar{y})^2}"""
    )
    st.write(
        "RSR: Root Mean Standard Deviation Ratio. The root mean squared error (RMSE) normalized by the standard deviation of observations."
    )
    st.latex(r"""RSR = \frac{RMSE}{\sigma_{obs}}""")
    st.write(
        "PBIAS: Percent Bias. Useful to identify systematic over or under predictions. Percentage units."
    )
    st.latex(
        r"""PBIAS = 100\frac{\sum_{i=1}^{n}(y_i - \hat{y}_i)}{\sum_{i=1}^{n}(y_i)}"""
    )
    st.write(
        "PPE: Peak Percent Error. Evaluates the absolute percent error between the modeled and observed hydrographs peaks."
    )
    st.latex(r"""PPE = 100 \frac{|\hat{y}_{peak} - y_{peak}|}{y_{peak}}""")


def pbias_score(obs_values: np.array, model_values: np.array):
    """
    Calculate the Percent Bias

    Parameters
    ----------
    obs_df : pandas dataframe
        Dataframe of observed streamflow data
    model_df : pandas dataframe
        Dataframe of modeled streamflow data
    Returns
    -------
    pbias : float
        Percent Bias
    """
    # calculate the standard deviation of the observed values
    obs_sum = np.sum(obs_values)
    if obs_sum == 0:
        return np.nan
    # calculate the root mean squared error
    diff_sum = np.sum(obs_values - model_values)
    # calculate the root mean standard deviation ratio
    pbias_val = abs(diff_sum / obs_sum)
    pbias_val = pbias_val * 100
    return pbias_val


def calc_metrics(df: pd.DataFrame, target: str):
    """
    Calculate hydrograph statistics

    Parameters
    ----------
    df : pandas dataframe
        Dataframe containing observed and modeled flow or wse data
    target: str
        Column target variable for calculating the statistics.
        One of 'flow' or 'wse'

    Returns
    -------
    stats_df : pandas dataframe
        Dataframe of streamflow calibration statistics. Columns are the plan column id and the rows are the statistics
    """
    if target not in ["flow", "wse"]:
        raise ValueError("Target must be either 'flow' or 'wse'.")
    if (
        f"obs_{target}" not in df.columns
        or f"model_{target}" not in df.columns
        or "time" not in df.columns
    ):
        raise ValueError(
            f"Dataframe must contain 'obs_{target}', 'model_{target}' and 'time' columns. Current columns: {df.columns.tolist()}"
        )
    if df.empty:
        return pd.DataFrame()
    # set the beginning based on the model target
    df = df.dropna(subset=[f"model_{target}"])
    # time interpolate missing values
    df = df[["time", f"obs_{target}", f"model_{target}"]].copy()
    df = df.set_index("time").interpolate(method="time").reset_index()
    # drop any potential NaN values after interpolation
    df = df.dropna(subset=[f"obs_{target}", f"model_{target}"])
    if df.empty:
        st.warning(
            f"No data available for {target} after processing. Please check input data."
        )
        return pd.DataFrame()
    # create a regression metric object
    evaluator = RegressionMetric(
        y_true=df[f"obs_{target}"].values.reshape(-1, 1),
        y_pred=df[f"model_{target}"].values.reshape(-1, 1),
    )
    # calculate the r2
    r2_val = evaluator.R2()
    # calculate the nse
    nse_val = evaluator.nash_sutcliffe_efficiency()
    # calculate the rmse
    rmse_val = evaluator.root_mean_squared_error()
    # calculate the std dev
    std_dev_obs = np.std(df[f"obs_{target}"].values)
    # calculate the rsr
    rsr_val = rmse_val / std_dev_obs
    # calculate the pbias
    pbias_val = pbias_score(df[f"obs_{target}"].values, df[f"model_{target}"].values)
    # calculate the peak percent error
    pf_obs, pf_mod = (
        np.max(np.max(df[f"model_{target}"].values)),
        np.max(df[f"obs_{target}"].values),
    )
    ppe_val = (abs(pf_mod - pf_obs) / pf_obs) * 100
    # compile the statistics into a dataframe
    stats_df = pd.DataFrame(
        {
            "R2": [r2_val],
            "NSE": [nse_val],
            "RSR": [rsr_val],
            "PBIAS": [pbias_val],
            "PPE": [ppe_val],
        }
    )
    return stats_df


def eval_metrics(x):
    """
    Evaluate the calibration metrics according to the USACE guidelines and color code the evaluation,
    while keeping the original numeric values in the DataFrame.

    Parameters
    ----------
    x : pd.DataFrame
        DataFrame containing the calibration metrics. Columns include NSE, RSR, PBIAS, PFPE, and R2. Indices are the gage IDs.

    Returns
    -------
    styled_df : pd.io.formats.style.Styler
        Styled DataFrame with numeric values and color-coded cells based on evaluation.
    """
    # make a copy of the dataframe
    df = x.copy()

    # Color map for evaluation
    color_map = {
        "Very Good": "background-color: #4CAF50; color: white;",  # green
        "Good": "background-color: #8BC34A; color: black;",  # light green
        "Satisfactory": "background-color: #FFEB3B; color: black;",  # yellow
        "Unsatisfactory": "background-color: #F44336; color: white;",  # red
    }

    # Define evaluation functions for each metric
    def eval_r2(val):
        if val > 0.65 and val <= 1.0:
            return "Very Good"
        elif val > 0.55 and val <= 0.65:
            return "Good"
        elif val > 0.4 and val <= 0.55:
            return "Satisfactory"
        else:
            return "Unsatisfactory"

    def eval_nse(val):
        if val > 0.65 and val <= 1.0:
            return "Very Good"
        elif val > 0.55 and val <= 0.65:
            return "Good"
        elif val > 0.4 and val <= 0.55:
            return "Satisfactory"
        else:
            return "Unsatisfactory"

    def eval_rsr(val):
        if val > 0 and val <= 0.6:
            return "Very Good"
        elif val > 0.6 and val <= 0.7:
            return "Good"
        elif val > 0.7 and val <= 0.8:
            return "Satisfactory"
        else:
            return "Unsatisfactory"

    def eval_pbias(val):
        if val <= 15:
            return "Very Good"
        elif val >= 15 and val < 20:
            return "Good"
        elif val >= 20 and val < 30:
            return "Satisfactory"
        else:
            return "Unsatisfactory"

    def eval_ppe(val):
        if val <= 5:
            return "Very Good"
        elif val >= 5 and val < 10:
            return "Good"
        elif val >= 10 and val < 15:
            return "Satisfactory"
        else:
            return "Unsatisfactory"

    # Style function for each column
    def style_r2(col):
        return [color_map[eval_r2(v)] for v in col]

    def style_nse(col):
        return [color_map[eval_nse(v)] for v in col]

    def style_rsr(col):
        return [color_map[eval_rsr(v)] for v in col]

    def style_pbias(col):
        return [color_map[eval_pbias(v)] for v in col]

    def style_ppe(col):
        return [color_map[eval_ppe(v)] for v in col]

    styled_df = df.style
    if "R2" in df.columns:
        styled_df = styled_df.apply(style_r2, subset=["R2"])
    if "NSE" in df.columns:
        styled_df = styled_df.apply(style_nse, subset=["NSE"])
    if "RSR" in df.columns:
        styled_df = styled_df.apply(style_rsr, subset=["RSR"])
    if "PBIAS" in df.columns:
        styled_df = styled_df.apply(style_pbias, subset=["PBIAS"])
    if "PPE" in df.columns:
        styled_df = styled_df.apply(style_ppe, subset=["PPE"])
    styled_df = styled_df.format(precision=3)
    return styled_df
