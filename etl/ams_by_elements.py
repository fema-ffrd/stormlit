import pandas as pd
import geopandas as gpd
import duckdb
import logging

from dotenv import load_dotenv, find_dotenv
import boto3
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv(find_dotenv(".env"))
s3_client = boto3.client("s3")


def query_s3_ams_multi_element(
    _conn,
    pilot: str,
    realization_id: int,
    element_ids: list[str],
    block_group_start: int,
    block_group_end: int,
) -> pd.DataFrame:
    """
    Query peak flow data for multiple elements and block groups, combining results into one dataframe.

    Parameters:
        _conn (connection): A DuckDB connection object.
        pilot (str): The pilot name for the S3 bucket.
        realization_id (int): The realization ID to query (e.g., 1).
        element_ids (list[str]): The element IDs to query (e.g., ['amon-g-carter_s010']).
        block_group_start (int): The starting block group index to query.
        block_group_end (int): The ending block group index to query.
    Returns:
        pd.DataFrame: A pandas DataFrame containing the stochastic block group flow data.
    """
    s3_paths = [
        f"s3://{pilot}/cloud-hms-db/ams/realization={realization_id}/block_group={i}/peaks.pq"
        for i in range(block_group_start, block_group_end + 1)
    ]
    paths_str = ", ".join([f"'{p}'" for p in s3_paths])
    # Construct the query to read from multiple S3 paths
    query = f"""
        SELECT
            element,
            block_group,
            MAX(peak_flow) AS peak_flow,
            ARG_MAX(event_id, peak_flow) AS event_id
        FROM read_parquet([{paths_str}], hive_partitioning=true)
        --WHERE element in '{element_ids}'
        GROUP BY block_group, element
        ORDER BY peak_flow DESC;
    """
    return _conn.execute(query).fetch_df()


def query_by_element(_conn, element_id: str, pq_path: str):
    """Query the peak flow data for a specific element from the combined AMS dataset."""
    element_id = "amon-g-carter_s020"

    query = f"""
        SELECT  ROW_NUMBER() OVER (ORDER BY peak_flow DESC)  AS rank,
        peak_flow, element, block_group, event_id
        FROM read_parquet('{pq_path}')
        WHERE element = '{element_id}'
        ORDER BY peak_flow DESC;
    """

    return _conn.execute(query).fetch_df()


def list_elements(bucket: str, prefix: str) -> list[str]:
    """List all element names under a given S3 prefix, stripping the 'element=' prefix."""
    paginator = s3_client.get_paginator("list_objects_v2")
    elements = set()
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
        for cp in page.get("CommonPrefixes", []):
            key = cp.get("Prefix", "")
            # Example key: 'cloud-hms-db/simulations/element=amon-g-carter_s020/'
            if "element=" in key:
                element_name = key.split("element=")[1].split("/")[0]
                elements.add(element_name)
    return list(elements)


if __name__ == "__main__":
    bucket_name = "trinity-pilot"
    elements_prefix = "cloud-hms-db/simulations/"
    pq_output_path = "ams_by_elements.pq"

    con = duckdb.connect()
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    con.execute(
        f"""CREATE SECRET (TYPE s3, KEY_ID '{os.getenv("AWS_ACCESS_KEY_ID")}', SECRET '{os.getenv("AWS_SECRET_ACCESS_KEY")}', REGION 'us-east-1');"""
    )
    element_ids = list_elements(bucket_name, elements_prefix)

    logger.info(f"Querying for elements: {element_ids}")

    df = query_s3_ams_multi_element(
        con,
        pilot=bucket_name,
        realization_id=1,
        element_ids=element_ids,
        block_group_start=1,
        block_group_end=2000,
    )

    df.head()
    df.to_parquet(pq_output_path, index=False)

    con.close()
