from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Iterable, List, Optional

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


def _normalize_prefix(prefix: Optional[str]) -> str:
    if not prefix:
        return ""
    return str(prefix).strip().strip("/")


def _default_projects_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", "configs", "projects.yaml")


@st.cache_data
def load_projects() -> List[ProjectConfig]:
    env_json = os.getenv("STORMLIT_PROJECTS")
    config_path = os.getenv("STORMLIT_PROJECTS_FILE", _default_projects_path())

    if env_json:
        data = json.loads(env_json)
    else:
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


def project_s3_root(project: ProjectConfig) -> str:
    return f"s3://{project.bucket}"


def project_http_root(project: ProjectConfig) -> str:
    return f"https://{project.bucket}.s3.amazonaws.com"


def _join_prefix(prefix: str, path: str) -> str:
    prefix = _normalize_prefix(prefix)
    path = path.lstrip("/")
    if not prefix:
        return path
    if not path:
        return prefix
    return f"{prefix}/{path}"


def project_key_path(project: ProjectConfig, path: str) -> str:
    return _join_prefix(project.prefix, path)


def project_s3_path(project: ProjectConfig, path: str) -> str:
    key = _join_prefix(project.prefix, path)
    if not key:
        return project_s3_root(project)
    return f"{project_s3_root(project)}/{key}"


def project_http_path(project: ProjectConfig, path: str) -> str:
    key = _join_prefix(project.prefix, path)
    if not key:
        return project_http_root(project)
    return f"{project_http_root(project)}/{key}"
