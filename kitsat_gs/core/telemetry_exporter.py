"""
TelemetryExporter — writes TelemetryStore contents to CSV with Unix timestamps.

Output path: ~/Documents/Kitsat/data/telemetry_<YYYYMMDD_HHMMSS>.csv
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from loguru import logger

from kitsat_gs.core.telemetry_store import TelemetryStore


def export(store: TelemetryStore, path: Path | None = None) -> Path:
    """
    Export all channels in the store to a CSV file.
    Returns the path written to.
    """
    if path is None:
        out_dir = Path.home() / "Documents" / "Kitsat" / "data"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"telemetry_{ts}.csv"

    keys = store.keys()
    if not keys:
        logger.warning("TelemetryExporter: store is empty, nothing to export")
        return path

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["unix_timestamp", "channel", "value"])
        for key in sorted(keys):
            for sample in store.series(key):
                writer.writerow([f"{sample.timestamp:.3f}", key, sample.value])

    logger.info(f"Telemetry exported to {path}")
    return path
