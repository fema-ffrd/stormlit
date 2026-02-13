import icechunk
import xarray as xr
import streamlit as st


def open_repo(bucket: str, prefix: str, region: str = "us-east-1") -> xr.Dataset:
    """Open an Icechunk repository from an S3 bucket and prefix.

    Args:
        bucket (str): The S3 bucket name.
        prefix (str): The prefix within the S3 bucket.
        region (str, optional): The AWS region. Defaults to "us-east-1".

    Returns:
        repo (icechunk.Repository): The opened Icechunk repository.
    """
    # Open the icechunk repo to the latest snapshot on the "main" branch
    storage_config = icechunk.s3_storage(
        bucket=bucket,
        prefix=prefix,
        region=region,
    )
    repo = icechunk.Repository.open(storage_config)
    return repo


def open_session(repo: icechunk.Repository, branch: str = "main") -> xr.Dataset:
    """Open an FFRD storms session from an Icechunk repository.

    Args:
        repo (icechunk.Repository): The Icechunk repository.
        branch (str, optional): The branch to open. Defaults to "main".

    Returns:
        ds (xr.Dataset): The opened dataset for the specified session.
    """
    # Open a read-only session for a given branch
    try:
        session = repo.readonly_session(branch=branch)
    except Exception as e:
        st.error(f"Failed to open readonly session of Icechunk repository: {e}")
        return None
    # Use xarray to open the snapshot as Zarr
    try:
        ds = xr.open_zarr(session.store, consolidated=False)
    except Exception as e:
        st.error(f"Failed to open Zarr dataset from Icechunk repository: {e}")
        return None
    # Ensure that the FFRD projection is respected (important for rioxarray)
    ds = ds.set_coords("spatial_ref")
    # Ensure abs_time is a coordinate and compute it into memory
    if "abs_time" not in ds.coords:
        st.error("Dataset does not contain 'abs_time' coordinate.")
        return None
    ds = ds.assign_coords(abs_time=ds["abs_time"].load())
    return ds
