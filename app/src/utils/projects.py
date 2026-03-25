from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, List

import streamlit as st
import yaml


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    bucket: str
    catalog_name: str
    warehouse_prefix: str
    study_area_json: str
    transpo_domain_json: str


@st.cache_data
def load_projects(config_path: str) -> List[ProjectConfig]:
    with open(config_path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    raw_projects = data.get("projects", data)
    if not isinstance(raw_projects, Iterable):
        raise ValueError("Project configuration must be a list of projects.")

    projects: List[ProjectConfig] = []
    for entry in raw_projects:
        if not entry:
            continue
        name = entry.get("name")
        bucket = entry.get("bucket")
        catalog_name = entry.get("catalog_name")
        warehouse_prefix = entry.get("warehouse_prefix")
        if not name or not bucket:
            raise ValueError("Each project must include name and bucket.")
        if not catalog_name or not warehouse_prefix:
            raise ValueError(
                "Each project must include catalog_name and warehouse_prefix."
            )
        projects.append(
            ProjectConfig(
                name=str(name),
                bucket=str(bucket),
                catalog_name=str(catalog_name),
                warehouse_prefix=str(warehouse_prefix),
                study_area_json=str(entry.get("study-area-json")),
                transpo_domain_json=str(entry.get("transpo-domain-json")),
            )
        )

    if not projects:
        raise ValueError("No projects defined in Stormlit project configuration.")
    return projects
