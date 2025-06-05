import os
import pytest
import pandas as pd
import pandas.testing as pdt
import geopandas as gpd
from dotenv import load_dotenv

# Custom imports
from src.db.utils import create_pg_connection, get_pg_dsn, create_s3_connection
from src.db.pull import (
    query_s3_ref_lines,
    query_s3_ref_points,
    query_s3_obs_flow,
    query_s3_mod_flow,
    query_s3_mod_wse,
    query_pg_table_all,
    query_pg_table_filter,
)

testDir = os.path.dirname(
    os.path.realpath(__file__)
)  # located within the app/tests folder
dataDir = os.path.join(testDir, "data")  # data folder within the tests folder

load_dotenv()

# Global variables
TEST_PARQUET = os.path.join(dataDir, "parquet")
TEST_CSV = os.path.join(dataDir, "csv")
PG_CONNECTION = create_pg_connection()
S3_CONNECTION = create_s3_connection()
DSN = get_pg_dsn()
PILOT = "trinity-pilot"
TEST_MODEL = "blw-elkhart"
TEST_REF_LINE_ID = "gage_usgs_08065350"
EVENT_ID = "may2015"
GAGE_ID = "08062800"
TEST_PG_TABLE = "models_by_gage"
TEST_PG_SCHEMA = "flat_stac"


@pytest.mark.integration
def test_get_ref_line_geometry():
    """
    Test querying model reference line geometry from S3.
    """
    test_dataset_path = os.path.join(
        TEST_PARQUET, "blw-elkhart_ref_line_geometry_df.parquet"
    )
    test_dataset_df = gpd.read_parquet(test_dataset_path)
    test_ref_line_geometry_df = query_s3_ref_lines(
        S3_CONNECTION,  # S3 connection using DuckDB
        PILOT,  # Pilot name for the S3 bucket
        model_id=TEST_MODEL,  # HEC-RAS model ID
    )
    assert test_ref_line_geometry_df.equals(test_dataset_df), (
        "Reference line geometry data from S3 does not match expected data."
    )


@pytest.mark.integration
def test_get_ref_pt_geometry():
    """
    Test querying model reference point geometry from S3.
    """
    test_dataset_path = os.path.join(
        TEST_PARQUET, "blw-elkhart_ref_pt_geometry_df.parquet"
    )
    test_dataset_df = gpd.read_parquet(test_dataset_path)
    test_ref_pt_geometry_df = query_s3_ref_points(
        S3_CONNECTION,  # S3 connection using DuckDB
        PILOT,  # Pilot name for the S3 bucket
        model_id=TEST_MODEL,  # HEC-RAS model ID
    )
    assert test_ref_pt_geometry_df.equals(test_dataset_df), (
        "Reference point geometry data from S3 does not match expected data."
    )


@pytest.mark.integration
def test_get_obs_gage_flow():
    """
    Test querying observed gage flow data from S3.
    """
    test_dataset_path = os.path.join(TEST_CSV, "blw-elkhart_obs_flow_df.csv")
    test_dataset_df = pd.read_csv(test_dataset_path, index_col=0)
    test_dataset_df["flow"] = test_dataset_df["flow"].astype(float)
    test_obs_gage_flow_df = query_s3_obs_flow(
        S3_CONNECTION,  # S3 connection using DuckDB
        PILOT,  # Pilot name for the S3 bucket
        gage_id=GAGE_ID,  # Example gage ID
        event_id=EVENT_ID,  # Example event ID
    )
    test_obs_gage_flow_df["flow"] = test_obs_gage_flow_df["flow"].astype(float)
    pdt.assert_series_equal(
        test_obs_gage_flow_df["flow"].reset_index(drop=True),
        test_dataset_df["flow"].reset_index(drop=True),
        rtol=1e-3,
    )


@pytest.mark.integration
def test_get_modeled_gage_flow():
    """
    Test querying modeled flow data from S3.
    """
    test_dataset_path = os.path.join(TEST_CSV, "blw-elkhart_mod_flow_df.csv")
    test_dataset_df = pd.read_csv(test_dataset_path, index_col=0)
    test_dataset_df["flow"] = test_dataset_df["flow"].astype(float)
    test_mod_flow_df = query_s3_mod_flow(
        S3_CONNECTION,  # S3 connection using DuckDB
        PILOT,  # Pilot name for the S3 bucket
        ref_id=TEST_REF_LINE_ID,  # Example reference element ID
        event_id=EVENT_ID,  # Example event ID
    )
    test_mod_flow_df["flow"] = test_mod_flow_df["flow"].astype(float)
    pdt.assert_series_equal(
        test_mod_flow_df["flow"].reset_index(drop=True),
        test_dataset_df["flow"].reset_index(drop=True),
        rtol=1e-3,
    )


@pytest.mark.integration
def test_get_modeled_gage_wse():
    """
    Test querying modeled water surface elevation (WSE) data from S3.
    """
    test_dataset_path = os.path.join(TEST_CSV, "blw-elkhart_mod_wse_df.csv")
    test_dataset_df = pd.read_csv(test_dataset_path, index_col=0)
    test_dataset_df["wse"] = test_dataset_df["wse"].astype(float)
    test_mod_wse_df = query_s3_mod_wse(
        S3_CONNECTION,  # S3 connection using DuckDB
        PILOT,  # Pilot name for the S3 bucket
        ref_id=TEST_REF_LINE_ID,  # Example reference element ID
        event_id=EVENT_ID,  # Example event ID
    )
    test_mod_wse_df["wse"] = test_mod_wse_df["wse"].astype(float)
    pdt.assert_series_equal(
        test_mod_wse_df["wse"].reset_index(drop=True),
        test_dataset_df["wse"].reset_index(drop=True),
        rtol=1e-3,
    )


@pytest.mark.integration_postgres
def test_get_models_by_gage_all():
    """
    Test querying geospatial gage metadata from Postgres.
    """
    test_dataset_path = os.path.join(TEST_PARQUET, "models_by_gage_all.parquet")
    test_dataset_gdf = gpd.read_parquet(test_dataset_path)
    test_models_by_gage_gdf = query_pg_table_all(
        PG_CONNECTION,  # Postgres connection using DuckDB
        DSN,  # DSN credentials for the PostgreSQL database
        TEST_PG_SCHEMA,  # Schema name where the table is located
        TEST_PG_TABLE,  # Table name to query
    )
    assert test_models_by_gage_gdf.equals(test_dataset_gdf), (
        "Gage metadata from Postgres does not match expected data."
    )


@pytest.mark.integration_postgres
def test_get_models_by_gage_filtered():
    """
    Test querying geospatial gage metadata from Postgres with filters.
    """
    test_dataset_path = os.path.join(TEST_PARQUET, "models_by_gage_filtered.parquet")
    test_dataset_gdf = gpd.read_parquet(test_dataset_path)
    test_models_by_gage_filtered_gdf = query_pg_table_filter(
        PG_CONNECTION,  # Postgres connection using DuckDB
        DSN,  # DSN credentials for the PostgreSQL database
        TEST_PG_SCHEMA,  # Schema name where the table is located
        TEST_PG_TABLE,  # Table name to query
        col_name="gage_id",  # Column to filter by
        search_id=GAGE_ID,  # ID to filter the column by
    )
    assert test_models_by_gage_filtered_gdf.equals(test_dataset_gdf), (
        "Filtered gage metadata from Postgres does not match expected data."
    )
