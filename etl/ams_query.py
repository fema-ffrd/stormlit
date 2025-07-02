import duckdb
import pandas as pd
import boto3
import os
import json
import time
from dotenv import load_dotenv, find_dotenv
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="query_log.log",
    filemode="a",
)

load_dotenv(find_dotenv(".env"))
s3_client = boto3.client("s3")


def s3_output_exists(bucket: str, key: str) -> bool:
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except s3_client.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise


def build_uris(storm_events, s3_response, bucket: str) -> list:
    uris = []
    for elem in s3_response.get("CommonPrefixes", []):
        element_id = elem["Prefix"].split("element=")[-1].split("/")[0]
        for year, event_id in storm_events:
            uri = f"s3://{bucket}/cloud-hms-db/simulations/element={element_id}/storm_id={year}/event_id={event_id}/FLOW.pq"
            uris.append(uri)
    return uris


def get_storm_events(storms_path, block):
    storms = pd.read_parquet(storms_path)
    block_storms = storms.loc[list(range(block["block_event_start"], block["block_event_end"] + 1))]
    storm_events = [(row["storm_id"], idx) for idx, row in block_storms.iterrows()]
    return storm_events


def process_block(block, storms_path, s3_response_dict, bucket, output_prefix):
    block_index = block["block_index"]
    try:
        con = duckdb.connect()
        con.execute("INSTALL httpfs")
        con.execute("LOAD httpfs")
        con.execute(
            f"""CREATE SECRET (TYPE s3, KEY_ID '{os.getenv("AWS_ACCESS_KEY_ID")}', SECRET '{os.getenv("AWS_SECRET_ACCESS_KEY")}', REGION 'us-east-1');"""
        )

        s3_output_key = f"{output_prefix}realization={block['realization_index']}/block_group={block_index}/peaks.pq"
        s3_output_path = f"s3://{bucket}/{s3_output_key}"

        if s3_output_exists(bucket, s3_output_key):
            logging.info(f"Skipping {s3_output_path} (already exists)")
            return None

        logging.info(f"Processing block {block_index}")
        storm_events = get_storm_events(storms_path=storms_path, block=block)

        start = time.time()
        uris = build_uris(storm_events, s3_response_dict, bucket)

        query = f"""
            SELECT element, event_id, MAX(values) as peak_flow
            FROM read_parquet({uris}, hive_partitioning=true)
            GROUP BY element, event_id
            ORDER BY peak_flow, event_id;
        """
        df = con.execute(query).fetch_df()
        df["rank"] = df.groupby("element")["peak_flow"].rank(method="first", ascending=False).astype(int)
        df.to_parquet(s3_output_path)
        logging.info(f"Block {block_index} processed in {time.time() - start:.2f}s")
        return None
    except Exception as e:
        logging.error(f"Failed processing block {block_index}: {e}")
        return block


def main(
    bucket,
    prefix,
    output_prefix,
    failed_blocks_path,
    storms_path,
    block_info_path,
):

    with open(block_info_path) as f:
        block_info_json = json.load(f)

    s3_response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter="/")

    failed_blocks = []
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(
                process_block,
                block,
                storms_path,
                s3_response,
                bucket,
                output_prefix,
            )
            for block in block_info_json
        ]

        for future in as_completed(futures):
            result = future.result()
            if result:
                failed_blocks.append(result)

    # Save failed blocks
    with open(failed_blocks_path, "w") as f:
        json.dump(failed_blocks, f, indent=2)
    logging.info(f"Done. {len(failed_blocks)} blocks failed.")


if __name__ == "__main__":
    bucket = "trinity-pilot"
    prefix = "cloud-hms-db/simulations/"
    output_prefix = "cloud-hms-db/ams/"
    failed_blocks_path = "failed_blocks.json"
    storms_path = "storms_4326.pq"
    block_info_path = "blocks_fixed_length.json"

    main(bucket, prefix, output_prefix, failed_blocks_path, storms_path, block_info_path)
