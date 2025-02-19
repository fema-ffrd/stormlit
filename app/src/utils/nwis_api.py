# -*- coding: utf-8 -*-

# Imports #####################################################################
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
        "data_type_cd",
        "begin_date",
        "end_date",
    ]

    df = df[keep_cols].copy()
    df = df.rename(columns={"dec_lat_va": "latitude", "dec_long_va": "longitude"})
    df["site_no"] = df["site_no"].astype(str)
    df["latitutde"] = df["latitude"].astype(float)
    df["longitude"] = df["longitude"].astype(float)
    # drop duplicate lat lons
    df = df.drop_duplicates(subset=["latitude", "longitude"])
    return df


def select_usgs_gages(
    gdf: gpd.GeoDataFrame,
    parameter: str = None,
    realtime: bool = True,
    data_type: str = "dv",
):
    """
    Using the pygeohydro NWIS wrapper for the usgs waterservice api,
    return a geodataframe of sites based on user define selections

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        The geometry to filter the sites by
    parameter : str
        One of Streamflow, Stage, or Precipitation
    realtime : bool
        True if only active sites are to be returned, False if all sites are to be returned
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
    elif parameter == "Precipitation":
        parameter_code = "00045"
    else:
        raise ValueError(
            "Invalid parameter. Must be one of 'Streamflow', 'Stage', or 'Precipitation'."
        )
    if data_type == "Daily":
        data_type = "dv"
    elif data_type == "Instantaneous":
        data_type = "iv"
    else:
        raise ValueError(
            "Invalid data type. Must be one of 'Daily' or 'Instantaneous'."
        )
    if realtime == "Active":
        site_status = "active"
    else:
        site_status = "all"

    # Filter the sites based on the user input
    bbox = list(
        gdf["geometry"].bounds.values.reshape(
            -1,
        )
    )
    bbox_str = f"{bbox[0]:.7f},{bbox[1]:.7f},{bbox[2]:.7f},{bbox[3]:.7f}"
    query = {
        "bBox": bbox_str,
        "outputDataTypeCd": data_type,
        "hasDataTypeCd": data_type,
        "parameterCd": parameter_code,
        "siteStatus": site_status,
    }
    try:
        # execute query
        query_gdf = nwis.get_info(query)
        query_gdf = format_gages_df(query_gdf)
        # convert to geodataframe
        query_gdf = gpd.GeoDataFrame(
            query_gdf,
            geometry=gpd.points_from_xy(query_gdf.longitude, query_gdf.latitude),
            crs="EPSG:4326",
        )

        # Ensure the polygon GeoDataFrame (gdf) is in the same CRS
        if gdf.crs != query_gdf.crs:
            gdf = gdf.to_crs(query_gdf.crs)

        # Filter to points that are within the exact polygon shape, not just the bounding box
        query_gdf = query_gdf[query_gdf.within(gdf.unary_union)].reset_index(drop=True)

        if len(query_gdf) == 0:
            return "No sites found for the selected geometry."
        else:
            return query_gdf
    except ZeroMatchedError as e:
        return f"No sites found for the selected geometry. Error: {e}"


def get_nwis_streamflow(station_id: str, dates: list, freq: str):
    """
    Get the streamflow data from the NWIS API

    Parameters
    ----------
    station_id : str
        The USGS station id
    dates : list
        The start and end dates for the data
    freq : str
        The frequency of the data, either Daily or Instantaneous

    Returns
    -------
    df : pd.DataFrame
        The streamflow data
    """
    # instantiate NWIS class
    nwis = NWIS()
    if freq == "Daily":
        freq = "dv"
    elif freq == "Instantaneous":
        freq = "iv"
    else:
        raise ValueError(
            "Invalid frequency. Must be one of 'Daily' or 'Instantaneous'."
        )
    df = nwis.get_streamflow([station_id], dates, mmd=False, freq=freq)
    return df
