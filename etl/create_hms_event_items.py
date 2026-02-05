import json
import pandas as pd
import requests
from pystac import Collection, Asset
from hecstac.events.hms_ffrd import HMSEventItem
from post_existing_collection import strip_collection_links_from_item
from stac_admin_client import AdminClient
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_inputs(storms_path, seeds_path, block_info_path):
    storms = pd.read_parquet(storms_path)
    seeds = pd.read_csv(seeds_path)
    with open(block_info_path) as f:
        blocks = json.load(f)
    return storms, seeds, blocks


def create_ffrd_properties(row, event_seed):
    return {
        "FFRD:storm_center_x": str(row["x"]),
        "FFRD:storm_center_y": str(row["y"]),
        "FFRD:storm_date": str(row["storm_date"]),
        "FFRD:storm_duration": row["storm_duration"],
        "FFRD:storm_type": row["storm_type"],
        "FFRD:storm_id": row["storm_id"],
        "FFRD:basin_path": row["basin_path"],
        "FFRD:event_seed": event_seed,
    }


def build_collection(realization_idx, block_idx, realization_seed, block_seed):
    padded_realization = f"{realization_idx:02d}"
    padded_block = f"{block_idx:04d}"
    collection_id = f"r{padded_realization}-b{padded_block}"

    collection = Collection(
        id=collection_id,
        description=f"HMS simulations for realization {realization_idx} block group {block_idx}.",
        extent=None,
        extra_fields={
            "realization": realization_idx,
            "block_group": block_idx,
            "realization_seed": realization_seed,
            "block_seed": block_seed,
        },
    )

    collection.add_asset(
        "ams",
        Asset(
            href=f"s3://trinity-pilot/cloud-hms-db/ams/realization={realization_idx}/block_group={block_idx}/peaks.pq",
            title="ams",
            description="Parquet file containing AMS values for each element and event.",
            media_type="application/x-parquet",
        ),
    )
    return collection


def build_event_item(
    event_number,
    row,
    event_index_by_block,
    realization_idx,
    block_idx,
    source_paths,
    event_seed,
    authoritative_model_path,
):
    item = HMSEventItem(
        realization_idx,
        block_idx,
        event_number,
        row["storm_path"],
        row["basin_path"],
        str(row["storm_date"]),
        row["storm_id"],
        event_index_by_block,
        source_paths,
    )
    item.properties.update(create_ffrd_properties(row, event_seed))
    item.add_authoritative_model_link(authoritative_model_path)
    item.build_assets()
    item.add_storm_item_link()
    item.set_self_href(f"event_{event_number}.json")
    return item


def upload_collection(client: AdminClient, collection: Collection):
    collection_id = collection.id
    response = requests.get(
        client.collection_url.format(client.stac_endpoint, collection_id)
    )
    if response.status_code == 404:
        response = requests.post(
            client.collection_url.format(client.stac_endpoint, ""),
            json=collection.to_dict(),
            headers=client.auth_header,
        )
        response.raise_for_status()

        for item in collection.get_all_items():
            item_dict = strip_collection_links_from_item(item.to_dict())
            item_dict["collection"] = collection_id
            client.add_collection_item(collection_id, item_dict)


if __name__ == "__main__":
    storms_path = "storms_4326.pq"
    seeds_path = "seeds.csv"
    block_info_path = "blocks_fixed_length.json"
    authoritative_model_path = (
        "https://stac-api.arc-apps.net/collections/conformance-models/items/trinity"
    )

    source_paths = ["/home/sjanke/repos/hecstac/hms_events/trinity.json"]
    client = AdminClient("https://stac-api.arc-apps.net")

    storms, seeds, blocks = load_inputs(storms_path, seeds_path, block_info_path)
    for block in blocks:
        r_idx = block["realization_index"]
        b_idx = block["block_index"]
        logger.info(f"Processing r{r_idx:02d}-b{b_idx:04d}")

        event_ids_in_block = list(
            range(block["block_event_start"], block["block_event_end"] + 1)
        )
        block_storms = storms.loc[event_ids_in_block]
        block_seeds = seeds[seeds["Events"].isin(event_ids_in_block)]

        r_seed = str(block_seeds.iloc[0]["realization_seed"])
        b_seed = str(block_seeds.iloc[0]["block_seed"])

        collection = build_collection(r_idx, b_idx, r_seed, b_seed)

        for event_number, row in block_storms.iterrows():
            event_index_by_block = event_ids_in_block.index(event_number) + 1
            event_seed = str(
                seeds.loc[seeds["Events"] == event_number, "event_seed"].iloc[0]
            )
            item = build_event_item(
                event_number,
                row,
                event_index_by_block,
                r_idx,
                b_idx,
                source_paths,
                event_seed,
                authoritative_model_path,
            )
            collection.add_item(item)

        collection.update_extent_from_items()
        # upload_collection(client, collection)
