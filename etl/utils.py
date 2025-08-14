"""Utilities for the ETL module."""
from __future__ import annotations

import contextlib
import logging
import os
from typing import TYPE_CHECKING, Any

import duckdb
import geopandas as gpd
from dotenv import load_dotenv
from duckdb import DuckDBPyConnection

if TYPE_CHECKING:
    from collections.abc import Callable
    from logging import Logger

    from pandas import DataFrame


__all__ = [
    "AMSQueriesMixin",
    "BaseDuckDBParquetQuery",
    "DuckDBParquetQuery",
    "HMSQueriesMixin",
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


def _create_db_connection() -> DuckDBPyConnection:
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


class BaseDuckDBParquetQuery:
    """Base class for S3-based parquet data operations using DuckDB."""

    def __init__(self, bucket_name: str):
        """Initialize the S3 query builder.

        Parameters
        ----------
        bucket_name : str
            The S3 bucket name.

        """
        self.bucket_name = bucket_name
        self.db_conn = _create_db_connection()
        self._cached_data: dict[str, Any] = {}

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - closes connection if we own it."""
        self.close()

    def close(self):
        """Close the S3 connection."""
        if self.db_conn is not None:
            self.db_conn.close()

    def __del__(self):
        """Destructor to ensure connection is closed."""
        self.close()

    def _check_filepath(self, s3_path: str) -> None:
        """Check if a given path exists in the bucket.

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
            result = self.db_conn.execute("""
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
        self._check_filepath(s3_path)
        if params is None:
            params = [s3_path]
        return self.db_conn.execute(query, params).fetchdf()

    def _get_cached_property(self, cache_key: str, loader_func: Callable[[], Any]) -> Any:
        """Get a cached property value or load it if not cached.

        Parameters
        ----------
        cache_key : str
            The key to use for caching.
        loader_func : callable
            Function to call to load the data if not cached.

        Returns
        -------
        any
            The cached or newly loaded data.

        """
        if not callable(loader_func):
            raise TypeError("loader_func must be callable")

        if cache_key not in self._cached_data:
            self._cached_data[cache_key] = loader_func()
        return self._cached_data[cache_key]


class HMSQueriesMixin(BaseDuckDBParquetQuery):
    """Mixin for HMS-related query methods."""

    @property
    def hms_elements(self) -> dict[str, list[str]]:
        """Mapping of HMS elements to their associated USGS IDs.

        Returns
        -------
        dict[str, list[str]]
            Dictionary mapping HMS element names to lists of USGS IDs.

        """
        def _load_hms_elements():
            s3_path = f"s3://{self.bucket_name}/stac/prod-support/gages/hms_gages_lookup.parquet"
            self._check_filepath(s3_path)
            hms_lookup = gpd.read_parquet(s3_path)
            return (
                hms_lookup.groupby("HMS Element")["USGS ID"].apply(list).to_dict()
            )

        return self._get_cached_property("hms_elements", _load_hms_elements)

    @property
    def hms_storms(self) -> DataFrame:
        """Cached list of HMS storms (loaded once from S3 on first access).

        Returns
        -------
        pandas.DataFrame
            DataFrame with columns: event_id, storm_id, storm_type.

        """
        def _load_hms_storms():
            s3_path = f"s3://{self.bucket_name}/cloud-hms-db/storms.pq"
            query = """
                SELECT event_number as event_id, storm_id, storm_type
                FROM read_parquet(?, hive_partitioning=true);
            """
            return self._execute_query(s3_path, query)

        return self._get_cached_property("hms_storms", _load_hms_storms)


class AMSQueriesMixin(BaseDuckDBParquetQuery):
    """Mixin for AMS-related query methods."""

    @property
    def all_ams_gage_ids(self) -> list[str]:
        """List of all available AMS gage IDs.

        Returns
        -------
        list[str]
            List of gage IDs that have AMS data available.

        """
        def _load_all_ams_gage_ids():
            with contextlib.suppress(Exception):
                s3_pattern = f"s3://{self.bucket_name}/stac/prod-support/gages/*/*.pq"
                result = self.db_conn.execute("""
                    SELECT DISTINCT regexp_extract(file, '.*/([^/]+)/[^/]+\\.pq$', 1) as gage_id
                    FROM glob(?)
                    WHERE file LIKE '%-ams.pq'
                """, [s3_pattern]).fetchall()
                return [row[0] for row in result if row[0]]
            return []

        return self._get_cached_property("all_ams_gage_ids", _load_all_ams_gage_ids)

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
        s3_path = f"s3://{self.bucket_name}/stac/prod-support/gages/{gage_id}/{gage_id}-ams.pq"
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
        s3_path = f"s3://{self.bucket_name}/cloud-hms-db/ams/realization={realization_id}/ams_by_elements.pq"
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
        s3_path = f"s3://{self.bucket_name}/cloud-hms-db/ams/realization={realization_id}/confidence_limits.parquet"
        query = """
            SELECT * FROM read_parquet(?, hive_partitioning=true)
            WHERE duration=? and site_no=? and variable=?;
        """
        return self._execute_query(s3_path, query, [s3_path, duration, gage_id, variable])


class DuckDBParquetQuery(HMSQueriesMixin, AMSQueriesMixin):
    """A query builder for S3-based data operations using DuckDB."""

    def __init__(self, bucket_name: str):
        """Initialize the S3 query builder.

        Parameters
        ----------
        bucket_name : str
            The S3 bucket name.

        """
        super().__init__(bucket_name)
