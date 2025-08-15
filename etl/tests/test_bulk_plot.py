from __future__ import annotations

import shutil
from pathlib import Path

from bulk_plot import plot_all_hms_elements


def test_plot_all_hms_elements():
    plot_all_hms_elements(save_dir="plots")
    assert len(list(Path("plots").glob("*.png"))) == 95
    shutil.rmtree("plots")
