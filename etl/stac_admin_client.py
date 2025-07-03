"""A class for managing read and write operations on a STAC API."""

import json
import logging
import os
import re
import traceback
from typing import Union

import pystac_client
import requests
from dotenv import load_dotenv
from pystac import Catalog, CatalogType, TemporalExtent


class AdminClient:
    """pystac_client with functions to post, put, delete, etc."""

    def __init__(self, stac_endpoint: str) -> None:
        """Construct class."""
        self.stac_endpoint = stac_endpoint
        self.stac_client = pystac_client.Client.open(self.stac_endpoint, headers=self.auth_header)

        self.collection_url = "{}/collections/{}"
        self.item_url = "{}/collections/{}/items/{}"

    def __getattr__(self, name):
        """Delegate undefined methods to the underlying stac_client."""
        # Could subclass instead, but this works fine.
        return getattr(self.stac_client, name)

    @property
    def auth_header(self):
        """Get auth header for a given user."""
        load_dotenv()
        auth_server = os.getenv("AUTH_ISSUER")
        print(auth_server)
        client_id = os.getenv("AUTH_ID")
        client_secret = os.getenv("AUTH_SECRET")

        username = os.getenv("AUTH_USER")
        password = os.getenv("AUTH_USER_PASSWORD")

        auth_payload = f"username={username}&password={password}&client_id={client_id}&grant_type=password&client_secret={client_secret}"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": "Bearer null",
        }

        auth_response = requests.request("POST", auth_server, headers=headers, data=auth_payload)

        try:
            token = json.loads(auth_response.text)["access_token"]
        except KeyError:
            raise KeyError

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-ProcessAPI-User-Email": username,
        }

        return headers

    def api_to_local_catalog(self, out_path: str, catalog_filter: re.Pattern = re.compile("(.*?)")):
        """Copy a collection from a pystac-api to a local catalog."""
        collections = self.stac_client.get_collections()
        collections = [c for c in collections if catalog_filter.fullmatch(c.id) is not None]

        for c in collections:
            out_catalog = Catalog(
                id=c.id,
                description=c.description,
                title=c.title,
                stac_extensions=c.stac_extensions,
                extra_fields=c.extra_fields,
            )
            local_cat_dir = os.path.join(out_path, c.id)

            if os.path.exists(os.path.join(local_cat_dir, "catalog.json")):
                logging.info(f"Skipping {c.id}, catalog exists")
                return

            if not os.path.exists(local_cat_dir):
                os.makedirs(local_cat_dir)

            item_count = 0
            for item in c.get_all_items():
                item.set_parent(out_catalog)
                out_catalog.add_item(item)
                item_count += 1

            out_catalog.normalize_hrefs(local_cat_dir)
            out_catalog.save(catalog_type=CatalogType.SELF_CONTAINED)
            logging.info(f"Saved local catalog {c.id}")

    def update_collection(self, collection: dict):
        """Update remote collection with new data."""
        response = requests.put(
            self.collection_url.format(self.stac_endpoint, collection["id"]),
            json=collection,
            headers=self.auth_header,
        )
        response.raise_for_status()

    def add_collection(self, collection: Union[str, dict]) -> None:
        """Create new collection on the remote."""
        if isinstance(collection, str):
            collection_id = collection
            collection["id"] = collection_id
            collection["title"] = collection_id
            collection["description"] = f"HEC-RAS models for {collection_id}"
        elif isinstance(collection, dict):
            collection_id = collection["id"]

        # check if exists first
        response = requests.get(self.collection_url.format(self.stac_endpoint, collection_id))
        if response.status_code != 404:
            return

        # Post new collection
        response = requests.post(
            self.collection_url.format(self.stac_endpoint, ""),
            json=collection,
            headers=self.auth_header,
        )
        response.raise_for_status()

    def remove_collection(self, stac_collection_id: str) -> None:
        """Remove a remote collection."""
        response = requests.delete(
            self.collection_url.format(self.stac_endpoint, stac_collection_id),
            headers=self.auth_header,
        )
        response.raise_for_status()

    def add_collection_item(self, stac_collection_id: str, item: dict) -> None:
        """Add an item to a remote collection."""
        response = requests.post(
            self.item_url.format(self.stac_endpoint, stac_collection_id, ""),
            json=item,
            headers=self.auth_header,
        )
        response.raise_for_status()

    def remove_collection_item(self, stac_collection_id: str, item_id: str) -> None:
        """Remove an item from a remote collection."""
        response = requests.delete(
            self.item_url.format(self.stac_endpoint, stac_collection_id, item_id),
            headers=self.auth_header,
        )
        response.raise_for_status()

    def update_collection_item(self, stac_collection_id: str, item: dict) -> None:
        """Update an item in a remote collection."""
        response = requests.put(
            self.item_url.format(self.stac_endpoint, stac_collection_id, item["id"]),
            json=item,
            headers=self.auth_header,
        )
        response.raise_for_status()
