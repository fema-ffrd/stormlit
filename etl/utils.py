"""Utilities for the ETL module."""
from __future__ import annotations

import contextlib
import logging
import os
from typing import TYPE_CHECKING

import duckdb
import geopandas as gpd
from dotenv import load_dotenv
from duckdb import DuckDBPyConnection

if TYPE_CHECKING:
    from logging import Logger

    from pandas import DataFrame



__all__ = [
    "S3QueryBuilder",
    "get_logger",
]

load_dotenv()

def get_logger(verbose: bool = False) -> Logger:
    """Get a logger instance with either DEBUG or INFO level."""
    verbose = os.getenv("STORMLIT_DEBUG", str(verbose)).lower() == "true"

    logger = logging.getLogger("etl")
    if verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


def _get_env(*keys: str, default: str = "") -> str:
    """Get environment variable value by key."""
    for key in keys:
        value = os.getenv(key)
        if value:
            return value
    return default


def _create_s3_connection() -> DuckDBPyConnection:
    """Create a connection to an S3 account using DuckDB.

    This function uses the AWS extension with credential_chain
    provider to automatically fetch credentials using AWS SDK
    default provider chain, supporting ECS instance credentials.

    Returns
    -------
    duckdb.DuckDBPyConnection
        DuckDB connection object configured for S3 access.

    """
    conn = duckdb.connect()
    conn.execute("INSTALL 'aws'")
    conn.execute("LOAD 'aws'")
    conn.execute("INSTALL 'httpfs'")
    conn.execute("LOAD 'httpfs'")

    aws_region = _get_env("AWS_REGION", "AWS_DEFAULT_REGION", default="us-east-1")
    conn.execute(
        """
        CREATE OR REPLACE SECRET aws_secret (
            TYPE s3,
            PROVIDER credential_chain,
            REGION ?
        )
        """,
        [aws_region],
    )
    return conn


class S3QueryBuilder:
    """A query builder for S3-based data operations using DuckDB."""

    def __init__(self, pilot: str):
        """Initialize the S3 query builder.

        Parameters
        ----------
        pilot : str
            The pilot name for the S3 bucket.

        """
        self.pilot = pilot
        self.s3_conn = _create_s3_connection()
        self._hms_elements = None
        self._all_ams_gage_ids = None
        self._hms_storms = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - closes connection if we own it."""
        self.close()

    def close(self):
        """Close the S3 connection."""
        if self.s3_conn is not None:
            self.s3_conn.close()

    def __del__(self):
        """Destructor to ensure connection is closed."""
        self.close()

    def _check_s3_path(self, s3_path: str) -> None:
        """Check if a given S3 path exists using DuckDB.

        Parameters
        ----------
        s3_path : str
            The S3 path to check.

        Raises
        ------
        FileNotFoundError
            If the S3 path does not exist.

        """
        try:
            result = self.s3_conn.execute("""
                SELECT COUNT(*) as file_count
                FROM glob(?)
            """, [s3_path]).fetchone()
        except Exception as e:
            if isinstance(e, FileNotFoundError):
                raise
            raise FileNotFoundError(f"S3 path {s3_path} does not exist or is inaccessible: {e!s}") from e

        if result is None or result[0] == 0:
            raise FileNotFoundError(f"S3 path {s3_path} does not exist.")

    def _execute_query(self, s3_path: str, query: str, params: list[str] | None = None) -> DataFrame:
        """Execute a query with S3 path validation.

        Parameters
        ----------
        s3_path : str
            The S3 path to validate and query.
        query : str
            The SQL query to execute.
        params : list, optional
            Query parameters. If None, defaults to [s3_path].

        Returns
        -------
        pandas.DataFrame
            Query results as a pandas DataFrame.

        Raises
        ------
        FileNotFoundError
            If the S3 path does not exist.

        """
        self._check_s3_path(s3_path)
        if params is None:
            params = [s3_path]
        return self.s3_conn.execute(query, params).fetchdf()

    @property
    def hms_elements(self) -> dict[str, list[str]]:
        """Mapping of HMS elements to their associated USGS IDs."""
        if self._hms_elements is None:
            hms_gages_lookup_uri = f"s3://{self.pilot}/stac/prod-support/gages/hms_gages_lookup.parquet"
            hms_lookup = gpd.read_parquet(hms_gages_lookup_uri)
            self._hms_elements = (
                hms_lookup.groupby("HMS Element")["USGS ID"].apply(list).to_dict()
            )
        return self._hms_elements

    @property
    def all_ams_gage_ids(self) -> list[str]:
        """List of all available AMS gage IDs."""
        if self._all_ams_gage_ids is None:
            with contextlib.suppress(Exception):
                s3_pattern = f"s3://{self.pilot}/stac/prod-support/gages/*/*.pq"
                result = self.s3_conn.execute("""
                    SELECT DISTINCT regexp_extract(file, '.*/([^/]+)/[^/]+\\.pq$', 1) as gage_id
                    FROM glob(?)
                    WHERE file LIKE '%-ams.pq'
                """, [s3_pattern]).fetchall()
                return [row[0] for row in result if row[0]]
        return []

    @property
    def hms_storms(self) -> DataFrame:
        """Cached list of HMS storms (loaded once from S3 on first access).

        Returns
        -------
        pandas.DataFrame
            Columns: event_id, storm_id, storm_type.

        """
        if self._hms_storms is None:
            s3_path = f"s3://{self.pilot}/cloud-hms-db/storms.pq"
            query = """
                SELECT event_number as event_id, storm_id, storm_type
                FROM read_parquet(?, hive_partitioning=true);
            """
            self._hms_storms = self._execute_query(s3_path, query)
        return self._hms_storms

    def gage_ams(self, gage_id: str) -> DataFrame:
        """Query AMS gage data from the S3 bucket.

        Parameters
        ----------
        gage_id : str
            The ID of the gage to query.

        Returns
        -------
        pandas.DataFrame
            A pandas DataFrame containing the AMS gage data with columns:
            peak_flow, gage_ht, gage_id, peak_time, rank.

        """
        s3_path = f"s3://{self.pilot}/stac/prod-support/gages/{gage_id}/{gage_id}-ams.pq"
        query = """
            SELECT
                peak_va as peak_flow,
                gage_ht,
                site_no as gage_id,
                datetime as peak_time,
                ROW_NUMBER() OVER (ORDER BY peak_flow DESC) AS rank
            FROM read_parquet(?, hive_partitioning=true);
        """
        return self._execute_query(s3_path, query)

    def ams_peaks_by_element(self, element_id: str, realization_id: int) -> DataFrame:
        """Query AMS peak data by element from the S3 bucket.

        Parameters
        ----------
        element_id : str
            The element ID to query.
        realization_id : int
            The realization ID to query.

        Returns
        -------
        pandas.DataFrame
            A pandas DataFrame containing the AMS peak data with columns:
            rank, element, peak_flow, event_id, block_group.

        """
        s3_path = f"s3://{self.pilot}/cloud-hms-db/ams/realization={realization_id}/ams_by_elements.pq"
        query = """
            SELECT ROW_NUMBER() OVER (ORDER BY peak_flow DESC) AS rank,
                   element, peak_flow, event_id, block_group
            FROM read_parquet(?, hive_partitioning=true)
            WHERE element=?;
        """
        return self._execute_query(s3_path, query, [s3_path, element_id])

    def ams_confidence_limits(
        self,
        gage_id: str,
        realization_id: int,
        duration: str,
        variable: str
    ) -> DataFrame:
        """Query confidence limits data from the S3 bucket for a given gage ID.

        Parameters
        ----------
        gage_id : str
            The gage ID to query.
        realization_id : int
            The realization ID to query.
        duration : str
            The duration of the confidence limits (e.g., '1Hour', '24Hour', '72Hour').
        variable : str
            The variable to query (e.g., 'Flow', 'Elev').

        Returns
        -------
        pandas.DataFrame
            A pandas DataFrame containing the confidence limits data with columns:
            site_no, variable, duration, AEP, return_period, computed, upper, lower.

        """
        s3_path = f"s3://{self.pilot}/cloud-hms-db/ams/realization={realization_id}/confidence_limits.parquet"
        query = """
            SELECT * FROM read_parquet(?, hive_partitioning=true)
            WHERE duration=? and site_no=? and variable=?;
        """
        return self._execute_query(s3_path, query, [s3_path, duration, gage_id, variable])
