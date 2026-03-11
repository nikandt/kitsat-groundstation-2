"""
TleParser — parse and validate TLE (Two-Line Element) sets.

Handles the standard 3-line format (title + line 1 + line 2).
Validates TLE checksums on both lines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Tle:
    name: str
    line1: str
    line2: str

    # Parsed fields (populated by parse())
    catalog_number: int = 0
    classification: str = "U"
    intl_designator: str = ""
    epoch_year: int = 0
    epoch_day: float = 0.0
    first_deriv_mean_motion: float = 0.0
    second_deriv_mean_motion: float = 0.0
    drag_term: float = 0.0
    ephemeris_type: int = 0
    element_set_number: int = 0

    inclination: float = 0.0       # degrees
    raan: float = 0.0              # degrees
    eccentricity: float = 0.0
    arg_of_perigee: float = 0.0    # degrees
    mean_anomaly: float = 0.0      # degrees
    mean_motion: float = 0.0       # revs/day
    rev_at_epoch: int = 0


def _tle_checksum(line: str) -> int:
    total = 0
    for ch in line[:68]:
        if ch.isdigit():
            total += int(ch)
        elif ch == "-":
            total += 1
    return total % 10


def _parse_decimal_assumed(s: str) -> float:
    """Parse a TLE decimal field that has an implicit leading '0.'."""
    s = s.strip()
    if not s or s in ("00000-0", "00000+0"):
        return 0.0
    sign = -1.0 if s.startswith("-") else 1.0
    s = s.lstrip("+-")
    if "-" in s:
        mantissa, exp = s.split("-")
        return sign * float("0." + mantissa) * 10 ** -int(exp)
    if "+" in s:
        mantissa, exp = s.split("+")
        return sign * float("0." + mantissa) * 10 ** int(exp)
    return sign * float("0." + s)


def parse(line1: str, line2: str, name: str = "") -> Tle:
    """
    Parse a TLE from two lines (and optional name/title line).
    Raises ValueError on checksum mismatch.
    """
    l1 = line1.strip()
    l2 = line2.strip()

    if len(l1) < 69 or len(l2) < 69:
        raise ValueError("TLE lines must be at least 69 characters")

    expected1 = _tle_checksum(l1)
    actual1 = int(l1[68])
    if expected1 != actual1:
        raise ValueError(f"Line 1 checksum mismatch: expected {expected1}, got {actual1}")

    expected2 = _tle_checksum(l2)
    actual2 = int(l2[68])
    if expected2 != actual2:
        raise ValueError(f"Line 2 checksum mismatch: expected {expected2}, got {actual2}")

    tle = Tle(name=name.strip(), line1=l1, line2=l2)

    # Line 1
    tle.catalog_number = int(l1[2:7].strip())
    tle.classification = l1[7]
    tle.intl_designator = l1[9:17].strip()
    tle.epoch_year = int(l1[18:20].strip())
    tle.epoch_day = float(l1[20:32].strip())
    tle.first_deriv_mean_motion = float(l1[33:43].strip())
    tle.second_deriv_mean_motion = _parse_decimal_assumed(l1[44:52].strip())
    tle.drag_term = _parse_decimal_assumed(l1[53:61].strip())
    tle.ephemeris_type = int(l1[62].strip() or "0")
    tle.element_set_number = int(l1[64:68].strip() or "0")

    # Line 2
    tle.inclination = float(l2[8:16].strip())
    tle.raan = float(l2[17:25].strip())
    tle.eccentricity = float("0." + l2[26:33].strip())
    tle.arg_of_perigee = float(l2[34:42].strip())
    tle.mean_anomaly = float(l2[43:51].strip())
    tle.mean_motion = float(l2[52:63].strip())
    tle.rev_at_epoch = int(l2[63:68].strip() or "0")

    return tle


def from_string(text: str) -> Optional[Tle]:
    """
    Parse TLE from a multi-line string (2 or 3 lines).
    Returns None on any parse/checksum error.
    """
    lines = [l for l in text.strip().splitlines() if l.strip()]
    try:
        if len(lines) == 3:
            return parse(lines[1], lines[2], name=lines[0])
        elif len(lines) == 2:
            return parse(lines[0], lines[1])
    except (ValueError, IndexError):
        return None
    return None
