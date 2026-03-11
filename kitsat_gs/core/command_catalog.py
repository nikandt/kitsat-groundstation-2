"""
CommandCatalog — loads sat_commands.csv and exposes a queryable catalog.

Prefers a local override at kitsat_gs/cfg/sat_commands.csv if present,
otherwise falls back to the file bundled with the installed kitsat package.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from loguru import logger


@dataclass(frozen=True)
class CommandDefinition:
    name: str
    target_id: int
    command_id: int
    param_type: str        # "", "int", "str", "int|int"
    explanation: str
    param_explanation: str


def _find_csv() -> Path:
    local = Path(__file__).parent.parent / "cfg" / "sat_commands.csv"
    if local.exists():
        return local
    try:
        import kitsat
        bundled = Path(kitsat.__file__).parent / "cfg" / "sat_commands.csv"
        if bundled.exists():
            return bundled
    except ImportError:
        pass
    raise FileNotFoundError("sat_commands.csv not found in local cfg/ or kitsat package")


@lru_cache(maxsize=1)
def load() -> list[CommandDefinition]:
    path = _find_csv()
    logger.debug(f"Loading command catalog from {path}")
    commands: list[CommandDefinition] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            commands.append(CommandDefinition(
                name=row["Command"].strip(),
                target_id=int(row["Target ID"].strip()),
                command_id=int(row["Command ID"].strip()),
                param_type=row["Parameters"].strip(),
                explanation=row["Explanation"].strip(),
                param_explanation=row.get("Parameter explanation", "").strip(),
            ))
    logger.debug(f"Loaded {len(commands)} commands")
    return commands


def get(name: str) -> Optional[CommandDefinition]:
    """Look up a command by name (case-insensitive)."""
    name_lower = name.lower()
    for cmd in load():
        if cmd.name.lower() == name_lower:
            return cmd
    return None


def all_names() -> list[str]:
    return [cmd.name for cmd in load()]


def by_target(target_id: int) -> list[CommandDefinition]:
    return [cmd for cmd in load() if cmd.target_id == target_id]
