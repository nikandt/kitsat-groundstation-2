"""Shared data models — TelemetryFrame, SatImage, CommandDef, CommandResult."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any

try:
    import numpy as np
    _NP = True
except ImportError:
    _NP = False


@dataclass
class TelemetryFrame:
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Temperatures (°C)
    temp_obc: float = 25.0
    temp_battery: float = 22.0
    temp_panel_x: float = 30.0
    temp_panel_y: float = 28.0
    temp_panel_z: float = 26.0

    # Power
    battery_percent: float = 85.0
    battery_voltage: float = 8.2
    solar_current_ma: float = 450.0
    power_consumption_mw: float = 800.0

    # Attitude (quaternion w, x, y, z)
    attitude_w: float = 1.0
    attitude_x: float = 0.0
    attitude_y: float = 0.0
    attitude_z: float = 0.0

    # Gyro rates (deg/s)
    gyro_x: float = 0.0
    gyro_y: float = 0.0
    gyro_z: float = 0.0

    # GNSS
    latitude: float = 0.0
    longitude: float = 0.0
    altitude_km: float = 550.0

    # Status
    mode: str = "nominal"
    uptime_s: int = 0
    packet_count: int = 0
    rssi_dbm: float = -80.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "temp_obc": self.temp_obc,
            "temp_battery": self.temp_battery,
            "temp_panel_x": self.temp_panel_x,
            "temp_panel_y": self.temp_panel_y,
            "temp_panel_z": self.temp_panel_z,
            "battery_percent": self.battery_percent,
            "battery_voltage": self.battery_voltage,
            "solar_current_ma": self.solar_current_ma,
            "power_consumption_mw": self.power_consumption_mw,
            "attitude_w": self.attitude_w,
            "attitude_x": self.attitude_x,
            "attitude_y": self.attitude_y,
            "attitude_z": self.attitude_z,
            "gyro_x": self.gyro_x,
            "gyro_y": self.gyro_y,
            "gyro_z": self.gyro_z,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude_km": self.altitude_km,
            "mode": self.mode,
            "uptime_s": self.uptime_s,
            "packet_count": self.packet_count,
            "rssi_dbm": self.rssi_dbm,
        }

    def get_field(self, name: str) -> Optional[Any]:
        return self.to_dict().get(name)


@dataclass
class SatImage:
    image_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    orbit_number: int = 0
    latitude: float = 0.0
    longitude: float = 0.0
    altitude_km: float = 550.0
    exposure_ms: int = 100
    mode: str = "visible"
    width: int = 320
    height: int = 240
    data: Optional[Any] = None       # numpy ndarray if numpy available
    thumbnail: Optional[Any] = None  # numpy ndarray if numpy available

    def metadata_str(self) -> str:
        return (
            f"ID: {self.image_id}\n"
            f"Time: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
            f"Orbit: {self.orbit_number}\n"
            f"Position: {self.latitude:.3f}°, {self.longitude:.3f}°\n"
            f"Altitude: {self.altitude_km:.1f} km\n"
            f"Exposure: {self.exposure_ms} ms\n"
            f"Mode: {self.mode}\n"
            f"Resolution: {self.width}×{self.height}"
        )


@dataclass
class CommandParam:
    name: str
    type: str   # "str", "int", "float", "bool", "enum"
    description: str = ""
    default: Any = None
    choices: Optional[List[str]] = None
    min_val: Optional[float] = None
    max_val: Optional[float] = None


@dataclass
class CommandDef:
    name: str
    description: str
    params: List[CommandParam] = field(default_factory=list)
    category: str = "general"
    dangerous: bool = False


@dataclass
class CommandResult:
    command: str
    success: bool
    timestamp: datetime = field(default_factory=datetime.utcnow)
    response: str = ""
    error: str = ""
    latency_ms: float = 0.0

    def __str__(self) -> str:
        status = "OK" if self.success else "ERR"
        ts = self.timestamp.strftime("%H:%M:%S")
        return f"[{ts}] [{status}] {self.command}: {self.response or self.error}"
