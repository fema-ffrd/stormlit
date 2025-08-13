"""HMS Flow Analysis Module.

This module provides functionality for querying and plotting all HMS
flow data from FFRD S3 storage, including AMS (Annual Maximum Series)
peaks and confidence limits.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from etl import utils
from etl.utils import S3QueryBuilder

__all__ = ["plot_all_hms_elements"]


logger = utils.get_logger()


def _plot_flow_aep(
    multi_event_ams_df: pd.DataFrame,
    gage_id: str,
    gage_ams_df: pd.DataFrame | None,
    gage_ams_confidence_df: pd.DataFrame | None,
    save_dir: Path,
    figsize: tuple[int, int],
    dpi: int,
) -> None:
    """Plot Discharge Frequency Plot using matplotlib.

    This creates a dual-axis structure:
    - Bottom x-axis: AEP (inverted, log scale)
    - Top x-axis: Return Period (log scale)
    - Both plot the same data points, just with different x-axis scaling

    Parameters
    ----------
    multi_event_ams_df : pandas.DataFrame
        DataFrame containing the multi event AEP, Return Period,
        and Peak Flow data with columns: ``aep``, ``return_period``,
        ``peak_flow``.
    gage_id : str
        The gage ID for plot title and filename.
    gage_ams_df : pandas.DataFrame or None
        DataFrame containing the gage AEP, Return Period, and Peak Flow data
        with columns: ``aep``, ``return_period``, ``peak_flow``.
    gage_ams_confidence_df : pandas.DataFrame or None
        DataFrame containing the gage AMS confidence limits
        with columns: ``site_no``, ``variable``, ``duration``, ``AEP``,
        ``return_period``, ``computed``, ``upper``, ``lower``.
    save_dir : pathlib.Path
        Directory path to save the PNG file.
    figsize : tuple[int, int]
        Figure size (width, height) in inches.
    dpi : int
        Dots per inch (DPI) for the saved image.

    """
    if multi_event_ams_df.empty:
        logger.warning(f"No data available for gage {gage_id} in the dataset.")
        return

    fig, ax_bottom = plt.subplots(figsize=figsize, layout="constrained")
    ax_top = ax_bottom.twiny()

    ax_bottom.set_xscale("log")
    ax_top.set_xscale("log")
    ax_bottom.set_yscale("log")

    # Plot modeled data
    ax_top.scatter(
        multi_event_ams_df["return_period"],
        multi_event_ams_df["peak_flow"],
        color="red",
        label="Modeled",
        s=50,
        alpha=0.8,
        zorder=5,
    )

    # Plot confidence limits if available
    if gage_ams_confidence_df is not None and not gage_ams_confidence_df.empty:
        ax_top.plot(
            gage_ams_confidence_df["return_period"],
            gage_ams_confidence_df["upper"],
            color="black",
            linestyle="--",
            linewidth=1,
            label="Confidence Limits",
            alpha=0.7,
        )
        ax_top.plot(
            gage_ams_confidence_df["return_period"],
            gage_ams_confidence_df["lower"],
            color="black",
            linestyle="--",
            linewidth=1,
            alpha=0.7,
        )

        ax_top.scatter(
            gage_ams_confidence_df["return_period"],
            gage_ams_confidence_df["computed"],
            color="blue",
            label="Computed",
            s=50,
            alpha=0.8,
            zorder=5,
        )

        # Invisible scatter to set axis limits
        ax_bottom.scatter(
            gage_ams_confidence_df["AEP"], gage_ams_confidence_df["upper"], alpha=0, s=0
        )
    elif gage_ams_df is not None and not gage_ams_df.empty:
        # Plot observed data if no confidence limits
        ax_bottom.scatter(
            gage_ams_df["aep"],
            gage_ams_df["peak_flow"],
            color="blue",
            label="Observed",
            s=50,
            alpha=0.8,
            zorder=5,
        )

    # Invisible scatter to set axis limits for modeled data
    ax_bottom.scatter(multi_event_ams_df["aep"], multi_event_ams_df["peak_flow"], alpha=0, s=0)

    ax_bottom.set_xlabel("AEP")
    ax_top.set_xlabel("Return Period (Years)")
    ax_bottom.set_ylabel("Peak Flow")
    ax_bottom.set_title(f"Discharge Frequency Curve ({gage_id})", pad=20)

    # Set axis limits based on return periods
    all_return_periods = multi_event_ams_df["return_period"].tolist()
    if gage_ams_df is not None and not gage_ams_df.empty:
        all_return_periods.extend(gage_ams_df["return_period"].tolist())
    if gage_ams_confidence_df is not None and not gage_ams_confidence_df.empty:
        all_return_periods.extend(gage_ams_confidence_df["return_period"].tolist())

    if all_return_periods:
        rp_min = min(all_return_periods)
        rp_max = max(all_return_periods)
        ax_top.set_xlim(rp_min * 0.5, rp_max * 2)

        # Set AEP axis (bottom) - inverted relationship: AEP = 1/Return_Period
        aep_max = 1 / (rp_min * 0.5)  # Large AEP corresponds to small RP
        aep_min = 1 / (rp_max * 2)  # Small AEP corresponds to large RP
        ax_bottom.set_xlim(aep_max, aep_min)  # This creates the "inverted" effect

    ax_bottom.grid(True, alpha=0.3)
    handles1, labels1 = ax_bottom.get_legend_handles_labels()
    handles2, labels2 = ax_top.get_legend_handles_labels()

    # Combine legends and position at bottom center
    all_handles = handles1 + handles2
    all_labels = labels1 + labels2

    if all_handles:
        ax_bottom.legend(
            all_handles,
            all_labels,
            bbox_to_anchor=(0.5, -0.15),
            loc="upper center",
            bbox_transform=ax_bottom.transAxes,
            ncol=len(all_handles),
        )

    save_path = Path(save_dir) / f"discharge_frequency_{gage_id}.png"
    fig.savefig(save_path, dpi=dpi, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close(fig)
    logger.info(f"Saved plot: {save_path}")


def _save_empty_plot(
    gage_id: str, reason: str, save_dir: Path, figsize: tuple[int, int], dpi: int
) -> None:
    """Save an empty plot with explanatory text when data is not available."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=figsize, layout="constrained")
    ax.text(
        0.5,
        0.5,
        f"Plot not available\n\nReason: {reason}",
        horizontalalignment="center",
        verticalalignment="center",
        transform=ax.transAxes,
        fontsize=14,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "lightgray", "alpha": 0.8},
    )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(f"Discharge Frequency Curve ({gage_id})", fontsize=16, pad=20)

    # Remove spines
    for spine in ax.spines.values():
        spine.set_visible(False)

    filename = save_dir / f"discharge_frequency_{gage_id}.png"
    fig.savefig(filename, dpi=dpi, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close(fig)
    logger.info(f"Saved empty plot for {gage_id}: {filename}")


def plot_all_hms_elements(
    *,
    bucket_name: str = "trinity-pilot",
    realization_id: int = 1,
    duration: str = "72Hour",
    variable: str = "Flow",
    save_dir: str | Path = "plots",
    figsize: tuple[int, int] = (12, 8),
    dpi: int = 300,
) -> None:
    """Plot discharge frequency curves for all HMS elements with associated USGS gages.

    This function queries HMS data from S3, matches elements with USGS gages,
    and generates discharge frequency plots comparing modeled vs observed data
    with confidence limits where available. When data is not available, saves
    empty plots with explanatory text.

    Parameters
    ----------
    bucket_name : str, defaults to "trinity-pilot"
        The S3 bucket name containing the HMS data.
    realization_id : int, defaults to 1
        The realization ID to query from the HMS database.
    duration : str, defaults to ``72Hour``
        The duration for confidence limits (e.g., ``1Hour``, ``24Hour``, ``72Hour``).
    variable : str, defaults to "Flow"
        The variable to query for confidence limits (e.g., ``Flow``, ``Elev``).
    save_dir : str or pathlib.Path, defaults to "./plots"
        The directory to save output plots.
    figsize : tuple of two ints, defaults to (12, 8)
        The figure size for the plots.
    dpi : int, defaults to 300
        The resolution of the plots in dots per inch (DPI).

    Raises
    ------
    Exception
        If there are issues connecting to S3 or querying data.

    """
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Starting HMS flow analysis for bucket: {bucket_name}")
    logger.info(
        f"Parameters: realization_id={realization_id}, duration={duration}, variable={variable}"
    )

    # To reduce the number of queries we filter out the stations that have no
    # folder containing AMS results. Note that although some stations have a
    # results folder but they may not contain the expected files.
    n_plots = 0
    with S3QueryBuilder(bucket_name) as s3_query:
        for element_id, usgs_ids in s3_query.hms_elements.items():
            logger.info(f"Processing HMS element: {element_id}")

            multi_event_ams_df = s3_query.ams_peaks_by_element(element_id, realization_id)

            if multi_event_ams_df.empty:
                logger.warning(f"No AMS data found for element {element_id}")
                for usgs_id in usgs_ids:
                    _save_empty_plot(
                        usgs_id,
                        f"No AMS data found for HMS element {element_id}",
                        save_dir,
                        figsize,
                        dpi,
                    )
                continue

            multi_event_ams_df["aep"] = multi_event_ams_df["rank"] / len(multi_event_ams_df)
            multi_event_ams_df["return_period"] = 1 / multi_event_ams_df["aep"]

            multi_event_ams_df = pd.merge(
                multi_event_ams_df, s3_query.hms_storms, left_on="event_id", right_on="event_id", how="left"
            )
            multi_event_ams_df["storm_id"] = pd.to_datetime(multi_event_ams_df["storm_id"]).dt.strftime(
                "%Y-%m-%d"
            )
            if not s3_query.all_ams_gage_ids:
                logger.warning(f"No AMS gage IDs found for HMS element {element_id}")
                continue

            for usgs_id in usgs_ids:
                if usgs_id not in s3_query.all_ams_gage_ids:
                    logger.debug(f"Skipping {usgs_id} - no AMS data available")
                    _save_empty_plot(
                        usgs_id, "No AMS data available for this gage", save_dir, figsize, dpi
                    )
                    continue

                logger.info(f"Processing gage: {usgs_id}")

                gage_ams_df = s3_query.ams_peaks_by_element(usgs_id, realization_id)

                if not gage_ams_df.empty:
                    gage_ams_df["aep"] = gage_ams_df["rank"] / len(gage_ams_df)
                    gage_ams_df["return_period"] = 1 / gage_ams_df["aep"]
                    gage_ams_df["peak_time"] = pd.to_datetime(gage_ams_df["peak_time"]).dt.strftime(
                        "%Y-%m-%d"
                    )

                gage_ams_confidence_df = s3_query.ams_confidence_limits(
                    gage_id=usgs_id,
                    realization_id=realization_id,
                    duration=duration,
                    variable=variable
                )

                if not gage_ams_confidence_df.empty:
                    if gage_ams_confidence_df["computed"].isna().all():
                        logger.warning(f"Skipping {usgs_id} - all computed values are NaNs")
                        _save_empty_plot(
                            usgs_id,
                            "All computed confidence limit values are NaN",
                            save_dir,
                            figsize,
                            dpi,
                        )
                        continue

                    gage_ams_confidence_df = gage_ams_confidence_df.drop_duplicates(subset=["AEP"])
                    gage_ams_confidence_df["return_period"] = 1 / gage_ams_confidence_df["AEP"]

                    _plot_flow_aep(
                        multi_event_ams_df,
                        usgs_id,
                        gage_ams_df if not gage_ams_df.empty else None,
                        gage_ams_confidence_df,
                        save_dir,
                        figsize=figsize,
                        dpi=dpi,
                    )
                    n_plots += 1
                else:
                    logger.warning(f"No confidence limits data found for {usgs_id}")
                    _save_empty_plot(usgs_id, "No confidence limits data found", save_dir, figsize, dpi)

    logger.info(f"Analysis complete! Generated {n_plots} discharge frequency plots.")


if __name__ == "__main__":
    plot_all_hms_elements()
