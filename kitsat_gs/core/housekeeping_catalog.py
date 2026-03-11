"""
HousekeepingCatalog — loads housekeeping.csv and provides unit-converted
telemetry definitions.

Each row describes one measurement type, its subvalues (axes / channels),
units, and conversion factors (multiply then add offset).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from loguru import logger


@dataclass(frozen=True)
class HousekeepingDefinition:
    type: str               # e.g. "Attitude"
    subtype: str            # e.g. "Magnetometer"
    subvalues: list[str]    # e.g. ["x", "y", "z"]  or [] for scalar
    units: str              # e.g. "Gs"
    multipliers: list[float]  # one per subvalue (or [1.0] for scalar)
    offsets: list[float]      # one per subvalue (or [0.0] for scalar)
    target_id: int
    command_id: int

    @property
    def full_name(self) -> str:
        return f"{self.type} / {self.subtype}"

    def convert(self, raw_values: list[float]) -> list[float]:
        """Apply unit conversion to a list of raw values."""
        result = []
        for i, v in enumerate(raw_values):
            m = self.multipliers[i] if i < len(self.multipliers) else 1.0
            o = self.offsets[i] if i < len(self.offsets) else 0.0
            result.append(v * m + o)
        return result


def _parse_pipe(value: str, cast=str) -> list:
    if not value.strip():
        return []
    return [cast(v.strip()) for v in value.split("|")]


@lru_cache(maxsize=1)
def load() -> list[HousekeepingDefinition]:
    path = Path(__file__).parent.parent / "cfg" / "housekeeping.csv"
    logger.debug(f"Loading housekeeping catalog from {path}")
    defs: list[HousekeepingDefinition] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            subvalues = _parse_pipe(row["Subvalues"])
            multipliers = _parse_pipe(row["Conversion factor, multiplication"], float)
            offsets = _parse_pipe(row["Conversion factor, offset"], float)
            # Scalar rows have single values, not pipe-separated
            if not multipliers:
                multipliers = [1.0]
            if not offsets:
                offsets = [0.0]
            defs.append(HousekeepingDefinition(
                type=row["Type"].strip(),
                subtype=row["Subtype"].strip(),
                subvalues=subvalues,
                units=row["Units"].strip(),
                multipliers=multipliers,
                offsets=offsets,
                target_id=int(row["TargetID"].strip()),
                command_id=int(row["CommandID"].strip()),
            ))
    logger.debug(f"Loaded {len(defs)} housekeeping definitions")
    return defs


def by_command(target_id: int, command_id: int) -> "HousekeepingDefinition | None":
    for d in load():
        if d.target_id == target_id and d.command_id == command_id:
            return d
    return None
