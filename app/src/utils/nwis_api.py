# -*- coding: utf-8 -*-

# Imports #####################################################################
import urllib.error
import socket
import time
import io
import urllib.request
import pandas as pd
import streamlit as st
import geopandas as gpd
from pygeohydro import NWIS
from pygeohydro.exceptions import ZeroMatchedError

# Functions ###################################################################


def format_gages_df(df: gpd.GeoDataFrame):
    """
    Format the gages_df to include only relevant columns

    Parameters
    ----------
    gages_df : gpd.GeoDataFrame
        The sites dataframe returned from the select_gages function

    Returns
    -------
    gages_df : gpd.GeoDataFrame
        The formatted sites dataframe

    """
    keep_cols = [
        "agency_cd",
        "site_no",
        "station_nm",
        "site_tp_cd",
        "dec_lat_va",
        "dec_long_va",
        "coord_acy_cd",
        "dec_coord_datum_cd",
        "alt_va",
        "alt_acy_va",
        "alt_datum_cd",
        "huc_cd",
    ]

    df = df[keep_cols].copy()
    df = df.rename(columns={"dec_lat_va": "latitude", "dec_long_va": "longitude"})
    df["site_no"] = df["site_no"].astype(str)
    df["latitutde"] = df["latitude"].astype(float)
    df["longitude"] = df["longitude"].astype(float)
    df = df.drop_duplicates(subset="site_no").reset_index(drop=True)
    return df


@st.cache_data
def select_usgs_gages(
    site_code: list,
    parameter: str,
    data_type: str = "iv",
):
    """
    Using the pygeohydro NWIS wrapper for the usgs waterservice api,
    return a geodataframe of sites based on user define selections

    Parameters
    ----------
    site_code : list
        List of USGS unique site number identifiers
    parameter : str
        One of Streamflow or Stage
    data_type : str
        One of iv or dv, iv for instantaneous values, dv for daily

    Returns
    -------
    query_gdf : gpd.GeoDataFrame
        sites with their associated information
    """
    # instantiate NWIS class
    nwis = NWIS()

    if parameter == "Streamflow":
        parameter_code = "00060"
    elif parameter == "Stage":
        parameter_code = "00065"
    else:
        st.error("Invalid parameter. Must be one of 'Streamflow' or 'Stage'.")
    # Filter by one or more site numbers
    if isinstance(site_code, list):
        gdf_list = []
        for site in set(site_code):
            query = {
                "sites": site,
                "outputDataTypeCd": data_type,
                "hasDataTypeCd": data_type,
                "parameterCd": parameter_code,
                "siteStatus": "all",
            }
            try:
                # execute query
                site_gdf = nwis.get_info(query)
                gdf_list.append(site_gdf)
            except ZeroMatchedError as e:
                st.warning(f"No metadata found for site {site}: {e}")
                return pd.DataFrame()
            except Exception as e:
                st.error(f"Service error for site {site}: {e}")
                return pd.DataFrame()
        if len(gdf_list) == 0:
            st.error("All sites returned no matching data based on user selection.")
            return pd.DataFrame()
        else:
            query_gdf = pd.concat(gdf_list)
            query_gdf = format_gages_df(query_gdf)
            return query_gdf
    else:
        st.error("Invalid input. Must provide a list of site codes.")


def parse_usgs_value_field(df, value_parameter_code):
    """
    Use the value_parameter_code to parse which field holds the values of interest

    Args:
        df (pd.DataFrame): any pandas dataframe with usgs data
        value_parameter_code (str): string sequence expected in end of column name holding values.
            USGS txt files often append a TS_ID to parameter codes. ex: 124212_00060 has a
            TS_ID of 124212 and usgs parameter code of 00060 (Discharge, cubic feet per second)
    Returns:
        value_field (str): pandas column name holding values associated with the parameter code
    """

    # Initialize the field variable
    value_field = None

    # find the value field
    for col in df.columns.values:
        if col.endswith(value_parameter_code):
            value_field = col

    return value_field


def exp_backoff(url: str, max_retries: int = 5):
    """
    Implement exponential backoff for an API call.
    This function retries the request up to 5 times, doubling the wait time after each failure.

    Args:
        url (str): The URL to query.
        max_retries (int): Maximum number of retries before giving up.
    Returns:
        response (urllib.response): The response object if successful, None otherwise.

    """
    for i in range(1, max_retries + 1):
        wait_time = 2**i
        try:
            response = urllib.request.urlopen(url, timeout=5)
            return response
        except (urllib.error.URLError, socket.timeout) as e:
            if i < max_retries:
                time.sleep(wait_time)
            else:
                st.error(f"Failed NWIS query after {max_retries} attempts: {e}")
                return None


@st.cache_data
def query_nwis(
    site: str,
    parameter: str,
    start_date: str,
    end_date: str,
    data_type: str,
    reference_df: pd.DataFrame,
    output_format: str = "rdb",
):
    """
    Retrieve instantaneous data for a usgs site, write to a file (optional, and return as a dataframe

    Args
        site (str): gage id of the USGS site, e.g. '12345678'
        parameter (str): one of [Streamflow, Stage]
        start_date (str): formatted to 'YYYY-MM-DD'
        end_date (str): formatted to 'YYYY-MM-DD'
        data_type (str): one of [iv, dv], iv for instantaneous values, dv for daily values
        reference_df (pd.DataFrame): dataframe with a 'time' column to use as a
        output_format (str): one of [rdb, waterML-2.0, json].
    Return
        df (pd.DataFrame): formatted dataframe of peak data
    """
    if parameter == "Streamflow":
        param_id = "00060"
    elif parameter == "Stage":
        param_id = "00065"
    else:
        st.error("Invalid parameter. Must be one of 'Streamflow' or 'Stage'.")
        return pd.DataFrame()
    try:
        # build url and make call only for USGS funded sites
        url = f"https://waterservices.usgs.gov/nwis/{data_type}/?format={output_format}&sites={site}&startDT={start_date}&endDT={end_date}&parameterCd={param_id}&siteType=ST&agencyCd=usgs&siteStatus=all"
        response = exp_backoff(url, max_retries=5)
        if response is None:
            return pd.DataFrame()
        # check that api call worked
        if response.status != 200:
            return pd.DataFrame()
        # decode results
        r = response.read()
        if output_format == "rdb":
            df = pd.read_table(
                io.StringIO(r.decode("utf-8")),
                comment="#",
                skip_blank_lines=True,
            )
            df = df.iloc[1:].copy()
        # determine the value field col id
        value_field = parse_usgs_value_field(df, param_id)
        if value_field is None:
            st.warning(
                f"No instantaneous data available for {parameter} from the provided site and event window."
            )
            return pd.DataFrame()
        # replace strings with NaN
        df[value_field] = pd.to_numeric(df[value_field], errors="coerce")
        if set(df["site_no"].isnull()) == {True}:
            st.warning(
                "No valid data found for the provided site. All site_no values are null."
            )
            return pd.DataFrame()
        else:
            if parameter == "Stage":
                target_col = "obs_stage"
                df = df.rename(columns={f"{value_field}": "obs_stage"})
            else:
                target_col = "obs_flow"
                df = df.rename(columns={f"{value_field}": "obs_flow"})
            df["time"] = df["datetime"].copy()
            df["time"] = pd.to_datetime(df["time"], utc=True)
            if not reference_df.empty:
                df["time"] = df["time"].dt.tz_convert(reference_df["time"].dt.tz)
                df = df[["time", target_col]].copy()
                gage_ts = df.merge(reference_df, on="time", how="outer")
                return gage_ts
            else:
                return df
    except Exception as e:
        st.error(f"Error processing the NWIS data: {e}")
        return pd.DataFrame()
