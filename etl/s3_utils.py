from __future__ import annotations

import json

import s3fs


def find_event_items(models_prefix: str):
    """Find event items in each "event=" in "model=" prefix. Used for finding RAS event items."""
    fs = s3fs.S3FileSystem(anon=False)
    valid_items = []

    # List all model= directories under the given prefix
    dirs = fs.ls(models_prefix, detail=True)
    model_dirs = [d["Key"] for d in dirs if "model=" in d["Key"]]

    for model_dir in model_dirs:
        # List all 'event=' directories under each model directory
        event_dirs = fs.ls(model_dir, detail=True)
        event_dirs = [e["Key"] for e in event_dirs if "event=" in e["Key"]]

        for event_dir in event_dirs:
            item_path = f"{event_dir}/item.json"
            if fs.exists(item_path):
                with fs.open(item_path, "r") as f:
                    try:
                        data = json.load(f)
                        if data.get("type") == "Feature":
                            valid_items.append(f"s3://{item_path}")
                    except json.JSONDecodeError:
                        pass
            else:
                pass

    return valid_items


def find_calibration_items(models_prefix: str):
    """Find calibration items in each "model=" prefix. Used for finding RAS model calibration items."""
    fs = s3fs.S3FileSystem(anon=False)

    valid_items = []
    # List all directories under the given prefix
    dirs = fs.ls(models_prefix, detail=True)
    model_dirs = [d["Key"] for d in dirs if "model=" in d["Key"]]
    for model_dir in model_dirs:
        item_path = model_dir + "/item.json"
        if fs.exists(item_path):
            with fs.open(item_path, "r") as f:
                try:
                    data = json.load(f)
                    if data.get("type") == "Feature":
                        valid_items.append(f"s3://{item_path}")
                    else:
                        pass
                except json.JSONDecodeError:
                    pass

    return valid_items
