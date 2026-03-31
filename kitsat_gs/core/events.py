"""Central event bus — all inter-component communication via Qt signals."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class EventBus(QObject):
    """Singleton Qt-signal-based event bus. All tabs subscribe here;
    no direct cross-module calls needed."""

    # Telemetry
    telemetry_updated = Signal(object)    # TelemetryFrame

    # Commands
    command_sent = Signal(str, dict)       # (command_name, params)
    command_response = Signal(object)      # CommandResult

    # Connection state
    connection_changed = Signal(str)       # "CONNECTED" | "SEARCHING" | "DISCONNECTED"

    # Orbit
    orbit_updated = Signal(dict)           # {lat, lon, alt, ground_track, aos, los, ...}

    # Images
    image_received = Signal(object)        # SatImage

    # Log / script output
    log_message = Signal(str)


_bus: "EventBus | None" = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
