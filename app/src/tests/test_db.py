import os
import sys
import pandas as pd
import pandas.testing as pdt
import geopandas as gpd
from dotenv import load_dotenv

load_dotenv()

testDir = os.path.dirname(
    os.path.realpath(__file__)
)  # located within the src/tests folder
dataDir = os.path.join(testDir, "data")  # data folder within the tests folder
srcDir = os.path.abspath(
    os.path.join(testDir, "..")
)  # go up one level into the src folder
sys.path.append(srcDir)  # add src folder to the system path

from db.utils import create_db_connection, get_pg_dsn, create_s3_connection
from db.pull import pull_from_db, pull_from_s3

# Global variables
TEST_PARQUET = os.path.join(dataDir, "parquet")
TEST_CSV = os.path.join(dataDir, "csv")
DB_CONNECTION = create_db_connection()
S3_CONNECTION = create_s3_connection()


def test_get_ref_line_geometry():
    """
    Test querying model reference line geometry from S3.
    """
    test_dataset_path = os.path.join(
        TEST_PARQUET, "blw-elkhart_ref_line_geometry_df.parquet"
    )
    test_dataset_df = gpd.read_parquet(test_dataset_path)
    test_ref_line_geometry_df = pull_from_s3(
        S3_CONNECTION,  # S3 connection using DuckDB
        query_type="geometry",  # query type
        model_id="blw-elkhart",  # HEC-RAS model ID
        geometry_type="Reference Lines",  # geometry type
    )
    assert test_ref_line_geometry_df.equals(test_dataset_df), (
        "Reference line geometry data from S3 does not match expected data."
    )


def test_get_ref_pt_geometry():
    """
    Test querying model reference point geometry from S3.
    """
    test_dataset_path = os.path.join(
        TEST_PARQUET, "blw-elkhart_ref_pt_geometry_df.parquet"
    )
    test_dataset_df = gpd.read_parquet(test_dataset_path)
    test_ref_pt_geometry_df = pull_from_s3(
        S3_CONNECTION,  # S3 connection using DuckDB
        query_type="geometry",  # query type
        model_id="blw-elkhart",  # HEC-RAS model ID
        geometry_type="Reference Points",  # geometry type
    )
    assert test_ref_pt_geometry_df.equals(test_dataset_df), (
        "Reference point geometry data from S3 does not match expected data."
    )


def test_get_obs_gage_flow():
    """
    Test querying observed gage flow data from S3.
    """
    test_dataset_path = os.path.join(TEST_CSV, "blw-elkhart_obs_gage_flow_df.csv")
    test_dataset_df = pd.read_csv(test_dataset_path, index_col=0)
    test_dataset_df["flow"] = test_dataset_df["flow"].astype(float)
    test_obs_gage_flow_df = pull_from_s3(
        S3_CONNECTION,  # S3 connection using DuckDB
        query_type="observed",  # query type
        var_type="flow",  # variable type
        event_id="may2015",  # calibration event
        gage_id="08062800",  # gage ID
    )
    test_obs_gage_flow_df["flow"] = test_obs_gage_flow_df["flow"].astype(float)
    pdt.assert_series_equal(
        test_obs_gage_flow_df["flow"].reset_index(drop=True),
        test_dataset_df["flow"].reset_index(drop=True),
        rtol=1e-3,
    )


def test_get_modeled_gage_flow():
    """
    Test querying modeled flow data from S3.
    """
    test_dataset_path = os.path.join(TEST_CSV, "blw-elkhart_modeled_gage_flow_df.csv")
    test_dataset_df = pd.read_csv(test_dataset_path, index_col=0)
    test_dataset_df["flow"] = test_dataset_df["flow"].astype(float)
    test_modeled_gage_flow_df = pull_from_s3(
        S3_CONNECTION,  # S3 connection using DuckDB
        query_type="modeled",  # query type
        var_type="flow",  # variable type
        event_id="may2015",  # calibration event
        ref_id="gage_usgs_08065350",  # reference element name
    )
    test_modeled_gage_flow_df["flow"] = test_modeled_gage_flow_df["flow"].astype(float)
    pdt.assert_series_equal(
        test_modeled_gage_flow_df["flow"].reset_index(drop=True),
        test_dataset_df["flow"].reset_index(drop=True),
        rtol=1e-3,
    )


def test_get_modeled_gage_wse():
    """
    Test querying modeled water surface elevation (WSE) data from S3.
    """
    test_dataset_path = os.path.join(TEST_CSV, "blw-elkhart_modeled_gage_wse_df.csv")
    test_dataset_df = pd.read_csv(test_dataset_path, index_col=0)
    test_dataset_df["wse"] = test_dataset_df["wse"].astype(float)
    test_modeled_gage_wse_df = pull_from_s3(
        S3_CONNECTION,  # S3 connection using DuckDB
        query_type="modeled",  # query type
        var_type="wse",  # variable type
        event_id="may2015",  # calibration event
        ref_id="gage_usgs_08065350",  # reference element name
    )
    test_modeled_gage_wse_df["wse"] = test_modeled_gage_wse_df["wse"].astype(float)
    pdt.assert_series_equal(
        test_modeled_gage_wse_df["wse"].reset_index(drop=True),
        test_dataset_df["wse"].reset_index(drop=True),
        rtol=1e-3,
    )


def test_get_models_by_gage_metadata():
    """
    Test querying geospatial gage metadata from Postgres.
    """
    test_dataset_path = os.path.join(TEST_PARQUET, "models_by_gage_df.parquet")
    test_dataset_df = gpd.read_parquet(test_dataset_path)
    test_models_by_gage_df = pull_from_db(
        DB_CONNECTION,  # Postgres connection using DuckDB
        get_pg_dsn(),  # Postgres credentials
        "models_by_gage",  # table name
        "Reference Lines",  # layer name
        "flat_stac",  # schema name
    )
    assert test_models_by_gage_df.equals(test_dataset_df), (
        "Gage metadata from Postgres does not match expected data."
    )
