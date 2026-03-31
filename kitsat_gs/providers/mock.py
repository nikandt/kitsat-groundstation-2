"""Mock data provider — 1 Hz telemetry with realistic noise, drift, and faults."""
from __future__ import annotations

import math
import random
import time
from datetime import datetime

from PySide6.QtCore import QTimer

from .base import DataProvider
from kitsat_gs.core.models import TelemetryFrame, CommandResult, SatImage
from kitsat_gs.core.events import get_event_bus

try:
    import numpy as np
    _NP = True
except ImportError:
    _NP = False


class MockProvider(DataProvider):
    """1 Hz mock provider with noise, drift, and simulated faults.

    Emits telemetry via the EventBus at ~1 second intervals.
    Handles all 20 registered commands with plausible responses.
    """

    _BASE_TEMP_OBC = 28.0
    _BASE_TEMP_BATT = 18.0
    _BASE_TEMP_PANEL = 35.0
    _BASE_BATTERY = 85.0
    _BASE_SOLAR = 420.0
    _BASE_POWER = 750.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bus = get_event_bus()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._interval_ms = 1000

        self._frame_count = 0
        self._start_time = time.time()
        self._connected = False

        self._battery = self._BASE_BATTERY
        self._drift_temp_obc = 0.0
        self._drift_temp_batt = 0.0
        self._attitude_phase = 0.0
        self._solar_angle = 0.0
        self._fault_active = False
        self._fault_countdown = 0

        self._lat = 0.0
        self._lon = 0.0
        self._alt = 550.0
        self._image_counter = 0

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._connected = True
        self._start_time = time.time()
        self._timer.start(self._interval_ms)
        self._bus.connection_changed.emit("CONNECTED")

    def stop(self) -> None:
        self._timer.stop()
        self._connected = False
        self._bus.connection_changed.emit("DISCONNECTED")

    def send_command(self, name: str, params: dict) -> None:
        latency = random.uniform(80, 400)
        QTimer.singleShot(
            int(latency),
            lambda: self._handle_command(name, params, latency)
        )

    @property
    def is_connected(self) -> bool:
        return self._connected

    def update_orbit_position(self, lat: float, lon: float, alt_km: float) -> None:
        self._lat = lat
        self._lon = lon
        self._alt = alt_km

    # ------------------------------------------------------------------
    # Internal tick
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        self._frame_count += 1
        uptime = int(time.time() - self._start_time)
        self._solar_angle += 0.5
        self._attitude_phase += 0.02

        # Temperature drift
        self._drift_temp_obc += random.gauss(0, 0.05)
        self._drift_temp_obc = max(-5.0, min(5.0, self._drift_temp_obc))
        self._drift_temp_batt += random.gauss(0, 0.03)
        self._drift_temp_batt = max(-3.0, min(3.0, self._drift_temp_batt))

        # Battery sinusoidal charge/discharge cycle
        solar_factor = max(0.0, math.sin(math.radians(self._solar_angle)))
        self._battery += solar_factor * 0.05 - 0.02
        self._battery = max(5.0, min(100.0, self._battery))

        # Random fault injection (~0.2% chance per tick)
        if not self._fault_active and random.random() < 0.002:
            self._fault_active = True
            self._fault_countdown = random.randint(3, 10)
        if self._fault_active:
            self._fault_countdown -= 1
            if self._fault_countdown <= 0:
                self._fault_active = False

        # Attitude quaternion (simulated slow rotation)
        phase = self._attitude_phase
        w = math.cos(phase * 0.5)
        x = math.sin(phase * 0.5) * 0.3
        y = math.sin(phase * 0.7) * 0.2
        z = math.sin(phase * 0.4) * 0.1
        norm = math.sqrt(w*w + x*x + y*y + z*z)
        w, x, y, z = w/norm, x/norm, y/norm, z/norm

        solar_current = self._BASE_SOLAR * solar_factor + random.gauss(0, 15)

        frame = TelemetryFrame(
            timestamp=datetime.utcnow(),
            temp_obc=self._BASE_TEMP_OBC + self._drift_temp_obc + random.gauss(0, 0.3),
            temp_battery=self._BASE_TEMP_BATT + self._drift_temp_batt + random.gauss(0, 0.2),
            temp_panel_x=self._BASE_TEMP_PANEL + solar_factor * 15 + random.gauss(0, 0.5),
            temp_panel_y=self._BASE_TEMP_PANEL + solar_factor * 12 + random.gauss(0, 0.5),
            temp_panel_z=self._BASE_TEMP_PANEL + solar_factor * 10 + random.gauss(0, 0.5),
            battery_percent=self._battery + random.gauss(0, 0.1),
            battery_voltage=7.4 + (self._battery / 100.0) * 1.2 + random.gauss(0, 0.02),
            solar_current_ma=max(0.0, solar_current),
            power_consumption_mw=(
                self._BASE_POWER + (50 if self._fault_active else 0) + random.gauss(0, 20)
            ),
            attitude_w=w, attitude_x=x, attitude_y=y, attitude_z=z,
            gyro_x=random.gauss(0, 0.08),
            gyro_y=random.gauss(0, 0.06),
            gyro_z=random.gauss(0, 0.05),
            latitude=self._lat,
            longitude=self._lon,
            altitude_km=self._alt,
            mode="fault" if self._fault_active else "nominal",
            uptime_s=uptime,
            packet_count=self._frame_count,
            rssi_dbm=-70.0 + random.gauss(0, 3.0),
        )
        self._bus.telemetry_updated.emit(frame)

    def _handle_command(self, name: str, params: dict, latency: float) -> None:
        uptime = int(time.time() - self._start_time)
        responses = {
            "PING": "PONG - link nominal",
            "GET_STATUS": f"Mode: nominal | Uptime: {uptime}s | Packets: {self._frame_count}",
            "REBOOT": "OBC rebooting... ETA 30s",
            "CAPTURE_IMAGE": self._mock_capture_image(params),
            "BEACON": "Beacon transmitted on 437.525 MHz",
            "DEPLOY_ANTENNA": "Antenna deployment sequence initiated",
            "SET_MODE": f"Mode set to {params.get('mode', 'nominal')}",
            "CALIBRATE_ATTITUDE": "Attitude calibration complete",
            "GET_TELEMETRY": "Telemetry dump queued",
            "RESET_FAULT": "Fault flags cleared",
            "ENABLE_PAYLOAD": f"Payload {params.get('payload_id', 'camera')} enabled",
            "DISABLE_PAYLOAD": f"Payload {params.get('payload_id', 'camera')} disabled",
            "START_LOGGING": f"Logging started at {params.get('interval_s', 10)}s interval",
            "STOP_LOGGING": "Logging stopped",
            "DOWNLOAD_LOG": f"Sending {params.get('count', 100)} records",
            "SET_TX_POWER": f"TX power set to {params.get('power_dbm', 27.0)} dBm",
            "SET_BEACON_INTERVAL": f"Beacon interval at {params.get('interval_s', 60)}s",
            "EMERGENCY_STOP": "EMERGENCY STOP executed",
            "RUN_SELF_TEST": "BIST passed: all subsystems nominal",
            "SET_ATTITUDE": (
                f"Attitude setpoint: R={params.get('roll_deg', 0):.1f} "
                f"P={params.get('pitch_deg', 0):.1f} "
                f"Y={params.get('yaw_deg', 0):.1f} deg"
            ),
        }
        response_text = responses.get(name, f"Command {name} acknowledged")
        result = CommandResult(
            command=name,
            success=True,
            response=response_text,
            latency_ms=latency,
        )
        self._bus.command_response.emit(result)

    def _mock_capture_image(self, params: dict) -> str:
        self._image_counter += 1
        mode = params.get("mode", "visible")
        exposure = params.get("exposure_ms", 100)
        h, w = 240, 320

        if _NP:
            import numpy as np
            img_data = np.zeros((h, w, 3), dtype=np.uint8)
            if mode == "visible":
                x_idx = np.arange(w)
                y_idx = np.arange(h)
                img_data[:, :, 0] = (x_idx / w * 200).astype(np.uint8)
                img_data[:, :, 1] = (y_idx[:, None] / h * 180).astype(np.uint8)
                img_data[:, :, 2] = 100
                img_data[:, ::32] = [255, 255, 255]
                img_data[::24, :] = [255, 255, 255]
            elif mode == "ir":
                cx, cy = w // 2, h // 2
                yy, xx = np.mgrid[0:h, 0:w]
                dist = np.sqrt((xx - cx)**2 + (yy - cy)**2)
                val = (255 * np.exp(-dist / 80)).astype(np.uint8)
                img_data[:, :, 0] = val
                img_data[:, :, 1] = val // 2
            else:
                img_data[:, :, 1] = np.random.randint(100, 200, (h, w), dtype=np.uint8)
                img_data[:, :, 0] = np.random.randint(20, 80, (h, w), dtype=np.uint8)

            noise = np.random.randint(-10, 10, img_data.shape, dtype=np.int16)
            img_data = np.clip(img_data.astype(np.int16) + noise, 0, 255).astype(np.uint8)
            thumbnail = img_data[::4, ::4].copy()
        else:
            img_data = None
            thumbnail = None

        sat_img = SatImage(
            image_id=f"IMG_{self._image_counter:04d}",
            timestamp=datetime.utcnow(),
            orbit_number=self._frame_count // 5580,
            latitude=self._lat,
            longitude=self._lon,
            altitude_km=self._alt,
            exposure_ms=exposure,
            mode=mode,
            width=w,
            height=h,
            data=img_data,
            thumbnail=thumbnail,
        )
        self._bus.image_received.emit(sat_img)
        return f"Image {sat_img.image_id} captured ({mode}, {exposure}ms)"
