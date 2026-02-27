from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, List

import streamlit as st
import yaml


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    bucket: str
    storm_metadata: str
    storm_collection: str
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
        if not name or not bucket:
            raise ValueError("Each project must include name and bucket.")
        projects.append(
            ProjectConfig(
                name=str(name),
                bucket=str(bucket),
                storm_metadata=str(entry.get("storm-metadata")),
                storm_collection=str(entry.get("storm-collection")),
                study_area_json=str(entry.get("study-area-json")),
                transpo_domain_json=str(entry.get("transpo-domain-json")),
            )
        )

    if not projects:
        raise ValueError("No projects defined in Stormlit project configuration.")
    return projects
