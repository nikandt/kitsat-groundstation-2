"""Command registry — singleton holding all 20 built-in satellite commands."""
from __future__ import annotations

from typing import Dict, Optional
from .models import CommandDef, CommandParam


class CommandRegistry:
    _instance: Optional["CommandRegistry"] = None
    _commands: Dict[str, CommandDef]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._commands = {}
            cls._instance._register_defaults()
        return cls._instance

    def register(self, cmd: CommandDef) -> None:
        self._commands[cmd.name] = cmd

    def get(self, name: str) -> Optional[CommandDef]:
        return self._commands.get(name)

    def all(self) -> Dict[str, CommandDef]:
        return dict(self._commands)

    def by_category(self, category: str) -> Dict[str, CommandDef]:
        return {k: v for k, v in self._commands.items() if v.category == category}

    def _register_defaults(self) -> None:
        cmds = [
            CommandDef("PING", "Check satellite connectivity", category="diagnostic"),
            CommandDef(
                "REBOOT",
                "Reboot the on-board computer",
                category="system",
                dangerous=True,
            ),
            CommandDef("GET_STATUS", "Request full status report", category="diagnostic"),
            CommandDef(
                "CAPTURE_IMAGE",
                "Take a photo with the imaging payload",
                params=[
                    CommandParam("mode", "enum", "Imaging mode", "visible",
                                 choices=["visible", "ir", "ndvi"]),
                    CommandParam("exposure_ms", "int", "Exposure time (ms)", 100,
                                 min_val=10, max_val=5000),
                ],
                category="payload",
            ),
            CommandDef("BEACON", "Transmit beacon packet", category="comm"),
            CommandDef(
                "DEPLOY_ANTENNA",
                "Trigger antenna deployment sequence",
                category="system",
                dangerous=True,
            ),
            CommandDef(
                "SET_MODE",
                "Change satellite operating mode",
                params=[
                    CommandParam("mode", "enum", "Operating mode", "nominal",
                                 choices=["nominal", "low_power", "safe", "science",
                                          "detumble"]),
                ],
                category="system",
            ),
            CommandDef("CALIBRATE_ATTITUDE", "Run attitude determination calibration",
                       category="adcs"),
            CommandDef(
                "SET_ATTITUDE",
                "Command attitude setpoint",
                params=[
                    CommandParam("roll_deg", "float", "Roll (deg)", 0.0),
                    CommandParam("pitch_deg", "float", "Pitch (deg)", 0.0),
                    CommandParam("yaw_deg", "float", "Yaw (deg)", 0.0),
                ],
                category="adcs",
            ),
            CommandDef("GET_TELEMETRY", "Request telemetry dump", category="diagnostic"),
            CommandDef("RESET_FAULT", "Clear fault flags", category="system"),
            CommandDef(
                "ENABLE_PAYLOAD",
                "Enable science payload power",
                params=[
                    CommandParam("payload_id", "enum", "Payload", "camera",
                                 choices=["camera", "magnetometer", "spectrometer"]),
                ],
                category="payload",
            ),
            CommandDef(
                "DISABLE_PAYLOAD",
                "Disable science payload power",
                params=[
                    CommandParam("payload_id", "enum", "Payload", "camera",
                                 choices=["camera", "magnetometer", "spectrometer"]),
                ],
                category="payload",
            ),
            CommandDef(
                "START_LOGGING",
                "Begin data logging to flash",
                params=[
                    CommandParam("interval_s", "float", "Log interval (s)", 10.0,
                                 min_val=1.0, max_val=3600.0),
                ],
                category="data",
            ),
            CommandDef("STOP_LOGGING", "Stop data logging", category="data"),
            CommandDef(
                "DOWNLOAD_LOG",
                "Request log segment download",
                params=[
                    CommandParam("start_idx", "int", "Start index", 0),
                    CommandParam("count", "int", "Number of records", 100),
                ],
                category="data",
            ),
            CommandDef(
                "SET_TX_POWER",
                "Set transmitter power level",
                params=[
                    CommandParam("power_dbm", "float", "Power (dBm)", 27.0,
                                 min_val=10.0, max_val=33.0),
                ],
                category="comm",
            ),
            CommandDef(
                "SET_BEACON_INTERVAL",
                "Set beacon transmission interval",
                params=[
                    CommandParam("interval_s", "float", "Interval (s)", 60.0,
                                 min_val=10.0, max_val=600.0),
                ],
                category="comm",
            ),
            CommandDef(
                "EMERGENCY_STOP",
                "Emergency halt of all non-critical systems",
                category="system",
                dangerous=True,
            ),
            CommandDef("RUN_SELF_TEST", "Execute built-in self-test (BIST)",
                       category="diagnostic"),
        ]
        for cmd in cmds:
            self.register(cmd)
