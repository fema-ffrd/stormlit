"""
Load a GeoJSON file from S3 into the ``model_source_data`` Iceberg table.

Each GeoJSON feature is stored as a single row with the following fixed schema:

    data_id  : unique identifier for the feature
    data     : JSON string of the feature's properties
    metadata : JSON string of source metadata (layer, s3_path, crs, lat, lon)
    assets   : JSON string of asset references (e.g. source S3 path)
    geometry : WKB binary of the feature geometry (EPSG:4326)

"""

import datetime as dt
import io
import json
import logging
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import s3fs
from connection import (
    connect_to_catalog,
    ensure_env_variables,
    load_config,
    postgres_connection_string,
    warehouse,
)
from dotenv import load_dotenv
from pyiceberg.schema import Schema
from pyiceberg.types import (
    BinaryType,
    NestedField,
    StringType,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixed Iceberg schema for model_source_data
# ---------------------------------------------------------------------------

MODEL_SOURCE_DATA_SCHEMA = Schema(
    NestedField(1, "data_id", StringType(), required=True),
    NestedField(2, "data", StringType(), required=False),
    NestedField(3, "metadata", StringType(), required=False),
    NestedField(4, "assets", StringType(), required=False),
    NestedField(5, "geometry", BinaryType(), required=False),
)


# ---------------------------------------------------------------------------
# GeoJSON → GeoDataFrame (mirrors app/src/db/pull.py)
# ---------------------------------------------------------------------------


def query_s3_geojson(s3_path: str) -> gpd.GeoDataFrame:
    """
    Read a GeoJSON file from S3 and return a GeoDataFrame reprojected to EPSG:4326.
    """
    fs = s3fs.S3FileSystem(anon=False)
    if not fs.exists(s3_path):
        raise FileNotFoundError(f"GeoJSON does not exist at {s3_path}")
    try:
        with fs.open(s3_path, "rb") as src:
            geojson_bytes = src.read()
        gdf = gpd.read_file(io.BytesIO(geojson_bytes))
    except Exception as exc:
        raise RuntimeError(f"Failed to read GeoJSON from {s3_path}: {exc}") from exc

    return gdf.to_crs(epsg=4326)


# ---------------------------------------------------------------------------
# GeoDataFrame → model_source_data rows
# ---------------------------------------------------------------------------


class _NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, (pd.Timestamp, dt.datetime)):
            return obj.isoformat() if not pd.isna(obj) else None
        return str(obj)


def _to_json(obj) -> str | None:
    if obj is None:
        return None
    try:
        return json.dumps(obj, cls=_NumpyEncoder)
    except Exception as exc:
        logger.warning("JSON serialisation failed (%s) — falling back to str()", exc)
        return str(obj)


def gdf_to_model_source_rows(
    gdf: gpd.GeoDataFrame,
    layer_name: str,
    s3_path: str,
) -> pa.Table:
    """
    Map a GeoDataFrame to the five-column ``model_source_data`` Arrow schema.

    Columns
    -------
    data_id  : ``<layer_name>_<index>`` or the feature ``id`` field when present
    data     : JSON string of the feature's non-geometry properties
    metadata : JSON string with layer, source path, CRS, and centroid lat/lon
    assets   : JSON string with the source S3 path
    geometry : WKB binary (EPSG:4326)
    """
    prop_cols = [c for c in gdf.columns if c != "geometry"]
    centroids = gdf.geometry.centroid

    data_ids, data_vals, metadata_vals, assets_vals, geom_vals = [], [], [], [], []

    for idx, row in gdf.iterrows():
        # data_id
        feature_id = row.get("id") if "id" in gdf.columns else None
        data_ids.append(
            str(feature_id) if feature_id is not None else f"{layer_name}_{idx}"
        )

        # data — all non-geometry properties
        props = {col: row[col] for col in prop_cols}
        data_vals.append(_to_json(props))

        # metadata — provenance / spatial context
        centroid = centroids.iloc[idx] if isinstance(idx, int) else centroids.loc[idx]
        metadata_vals.append(
            _to_json(
                {
                    "layer": layer_name,
                    "source": s3_path,
                    "crs": "EPSG:4326",
                    "lat": centroid.y,
                    "lon": centroid.x,
                }
            )
        )

        # assets — references to source files
        assets_vals.append(_to_json({"source": s3_path}))

        # geometry — WKB bytes
        geom = row.geometry
        geom_vals.append(geom.wkb if geom is not None else None)

    _schema = pa.schema(
        [
            pa.field("data_id", pa.string(), nullable=False),
            pa.field("data", pa.string(), nullable=True),
            pa.field("metadata", pa.string(), nullable=True),
            pa.field("assets", pa.string(), nullable=True),
            pa.field("geometry", pa.large_binary(), nullable=True),
        ]
    )
    return pa.table(
        {
            "data_id": pa.array(data_ids, type=pa.string()),
            "data": pa.array(data_vals, type=pa.string()),
            "metadata": pa.array(metadata_vals, type=pa.string()),
            "assets": pa.array(assets_vals, type=pa.string()),
            "geometry": pa.array(geom_vals, type=pa.large_binary()),
        },
        schema=_schema,
    )


# ---------------------------------------------------------------------------
# Iceberg table creation + data load
# ---------------------------------------------------------------------------


def load_to_iceberg(
    arrow_table: pa.Table,
    catalog,
    catalog_root: str,
    table_name: str,
    namespace: str,
) -> None:
    """
    Append ``arrow_table`` to an Iceberg table, creating it if it does not exist.

    The table is never dropped; successive loads accumulate rows so that
    ``model_source_data`` can store multiple GeoJSON sources.
    """
    iceberg_table_id = f"{namespace}.{table_name}"
    data_location = f"{catalog_root}/{namespace}/{table_name}"

    if catalog.table_exists(iceberg_table_id):
        logger.info("Table `%s` exists — will append.", iceberg_table_id)
        ice_table = catalog.load_table(iceberg_table_id)
    else:
        logger.info("Creating table `%s` …", iceberg_table_id)
        ice_table = catalog.create_table(
            identifier=iceberg_table_id,
            schema=MODEL_SOURCE_DATA_SCHEMA,
            location=data_location,
        )
        for col in MODEL_SOURCE_DATA_SCHEMA.columns:
            logger.info("  %s: %s", col.name, col.field_type)

    logger.info("Appending %d rows to `%s` …", len(arrow_table), iceberg_table_id)
    ice_table.append(arrow_table)
    logger.info("Done. Total rows written: %d", len(arrow_table))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(
    s3_path: str,
    layer_name: str,
    table_name: str,
    namespace: str,
    config: dict,
) -> None:
    catalog_root = warehouse(config["s3_bucket"], config["warehouse_prefix"])

    catalog = connect_to_catalog(
        pg_conn_string=postgres_connection_string(
            os.getenv("POSTGRES_HOST"),
            os.getenv("POSTGRES_PORT"),
            os.getenv("POSTGRES_USER"),
            os.getenv("POSTGRES_PASSWORD"),
            "stormlit_prod_db",
        ),
        catalog_name=config.get("catalog_name"),
        catalog_root=catalog_root,
        s3_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
        s3_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
        s3_region=os.getenv("S3_REGION"),
    )

    logger.info("Reading GeoJSON from %s …", s3_path)
    gdf = query_s3_geojson(s3_path)
    logger.info("Loaded %d features", len(gdf))

    arrow_table = gdf_to_model_source_rows(gdf, layer_name, s3_path)
    logger.info("Mapped to model_source_data schema (%d rows)", len(arrow_table))

    load_to_iceberg(arrow_table, catalog, catalog_root, table_name, namespace)


if __name__ == "__main__":
    load_dotenv()
    ensure_env_variables()
    CONFIG_FILE = os.path.join(
        os.getcwd(), "lakehouse/trinity/configs/storm-catalog.config.json"
    )
    config = load_config(CONFIG_FILE)
    main(
        s3_path="s3://south-platte/stac/storms_hydromet/hydro_domains/manual-transpo-area-v01_valid.json",
        layer_name="south_platte_transpo_domain",
        table_name="model_source_data",
        namespace="stac",
        config=config,
    )
