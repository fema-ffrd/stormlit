import json
from urllib.parse import urljoin

import fsspec
import pystac
import requests
from pystac import Collection, Item, Asset
from stac_admin_client import AdminClient
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def collection_from_file(s3_uri: str) -> Collection | None:
    """Load a STAC Collection from an S3 URI."""
    try:
        with fsspec.open(s3_uri, mode="r") as file:
            collection_dict = json.loads(file.read())
            return Collection.from_dict(collection_dict)
    except Exception as e:
        logger.error(f"Error reading STAC collection: {e}")
        return None


def item_dict_from_file(s3_uri: str) -> dict | None:
    """Load a STAC Item dictionary from an S3 URI."""
    try:
        with fsspec.open(s3_uri, mode="r") as file:
            return json.loads(file.read())
    except Exception as e:
        logger.error(f"Error reading STAC item: {e}")
        return None


def force_assets_absolute(collection: Collection, collection_root: str, bucket_name: str) -> Collection:
    """Convert all relative asset HREFs in a STAC Collection to absolute S3 or HTTP URLs."""
    if collection.is_relative():
        updated_assets = {}
        for key, asset in collection.get_assets().items():
            if "thumbnail" not in asset.roles:
                s3_url = f"{collection_root}/{asset.href}"
                updated_href = s3_url
            else:
                http_prefix = collection_root.replace(f"s3://{bucket_name}", f"https://{bucket_name}.s3.amazonaws.com")
                updated_href = f"{http_prefix}/{asset.href.replace('../', '')}"

            updated_assets[key] = Asset(
                href=updated_href, title=asset.title, media_type=asset.media_type, roles=asset.roles
            )

        collection.assets = updated_assets

    return collection


def strip_collection_links_from_item(item_dict: dict) -> dict:
    """Remove collection-level links from a STAC Item dictionary."""
    item_dict["links"] = [
        link for link in item_dict.get("links", []) if link["rel"] not in ["parent", "root", "collection"]
    ]
    return item_dict


def update_asset_hrefs_to_absolute(item: Item) -> Item:
    """Update all asset HREFs in a STAC Item to be absolute based on its self HREF."""
    self_href = item.get_self_href()
    logger.info(f"Item self HREF: {self_href}")

    updated_assets = {}
    for key, asset in item.get_assets().items():
        updated_href = urljoin(self_href, asset.href)
        updated_assets[key] = Asset(
            href=updated_href, title=asset.title, media_type=asset.media_type, roles=asset.roles
        )
        logger.info(f"Updated asset {key} href to: {updated_href}")

    item.assets = updated_assets
    return item


if __name__ == "__main__":
    bucket_name = "trinity-pilot"
    collection_root = f"s3://{bucket_name}/stac/prod-support/storms/72hr-events"
    s3_key = f"{collection_root}/collection.json"

    existing_collection = collection_from_file(s3_key)

    stac_api_url = "https://stac-api.arc-apps.net"
    client = AdminClient(stac_api_url)

    response = requests.get(client.collection_url.format(client.stac_endpoint, existing_collection.id))
    if response.status_code == 404:  # Add collection to API if not there
        response = requests.post(
            client.collection_url.format(client.stac_endpoint, ""),
            json=existing_collection.to_dict(),
            headers=client.auth_header,
        )
        response.raise_for_status()
    # Add each item
    for item in existing_collection.get_all_items():
        new_item = update_asset_hrefs_to_absolute(item)
        new_item_dict = strip_collection_links_from_item(new_item.to_dict())
        new_item_dict["collection"] = existing_collection.id
        client.add_collection_item(existing_collection.id, new_item_dict)
