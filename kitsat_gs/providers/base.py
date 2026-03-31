"""Abstract base class for all data providers."""
from __future__ import annotations

from PySide6.QtCore import QObject


class DataProvider(QObject):
    """Abstract base for all data providers (mock, USB, Bluetooth).

    QObject and ABCMeta have conflicting metaclasses, so abstract enforcement
    is done via NotImplementedError instead of abc.ABC.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

    def start(self) -> None:
        """Start data acquisition / simulation."""
        raise NotImplementedError

    def stop(self) -> None:
        """Stop data acquisition."""
        raise NotImplementedError

    def send_command(self, name: str, params: dict) -> None:
        """Send a command to the satellite (or simulate it)."""
        raise NotImplementedError

    @property
    def is_connected(self) -> bool:
        raise NotImplementedError
