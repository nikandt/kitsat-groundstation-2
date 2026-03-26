"""
ModemBridge — wraps the kitsat.lib.modem.Modem in a QThread so that
blocking queue reads don't freeze the UI.

Signals emitted on the Qt main thread:
    connected(port: str)
    disconnected()
    message_received(msg: list | str)
    error(text: str)
"""

from __future__ import annotations

from queue import Empty
from typing import Optional
from loguru import logger

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from kitsat.lib.modem import Modem


class _ReaderThread(QThread):
    """Polls modem._msg_queue and forwards messages as Qt signals."""

    message_received = Signal(object)

    def __init__(self, modem: Modem, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._modem = modem
        self._running = False

    def run(self) -> None:
        self._running = True
        while self._running:
            try:
                msg = self._modem.read(timeout=0.1)
                if msg is not None:
                    self.message_received.emit(msg)
            except Empty:
                pass
            except Exception as exc:
                logger.warning(f"Reader thread error: {type(exc).__name__}: {exc}")
                logger.opt(exception=True).debug("Reader thread traceback")

    def stop(self) -> None:
        self._running = False
        self.wait(2000)


class ModemBridge(QObject):
    """
    Qt-friendly wrapper around the kitsat Modem.

    Usage:
        bridge = ModemBridge()
        bridge.connected.connect(on_connected)
        bridge.message_received.connect(on_message)
        bridge.connect_auto()
    """

    connected = Signal(str)        # port name
    disconnected = Signal()
    message_received = Signal(object)   # list or str from packet_parser
    error = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._modem: Optional[Modem] = None
        self._reader: Optional[_ReaderThread] = None
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(2000)
        self._watchdog.timeout.connect(self._check_subprocess)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @Slot()
    def connect_auto(self) -> None:
        """Auto-detect and connect to satellite or groundstation."""
        self._setup_modem()
        logger.info("Attempting auto-connect...")
        result = self._modem.connect_auto()
        if result:
            port = self._modem.port or "unknown"
            logger.info(f"Connected to {port}")
            self._start_reader()
            self._watchdog.start()
            self.connected.emit(port)
        else:
            logger.warning("Auto-connect failed — no satellite or groundstation found")
            self.error.emit("No satellite or groundstation found on any serial port.")

    @Slot(str)
    def connect_port(self, port: str) -> None:
        """Connect to a specific serial port."""
        self._setup_modem()
        logger.info(f"Connecting to {port}...")
        result = self._modem.connect(port)
        if result:
            logger.info(f"Connected to {port}")
            self._start_reader()
            self._watchdog.start()
            self.connected.emit(port)
        else:
            logger.warning(f"Failed to connect to {port}")
            self.error.emit(f"Could not connect to {port}.")

    @Slot()
    def disconnect(self) -> None:
        """Disconnect from the current port."""
        self._watchdog.stop()
        if self._reader:
            self._reader.stop()
            self._reader = None
        if self._modem:
            try:
                self._modem.disconnect()
            except Exception as exc:
                logger.warning(f"Error during disconnect: {exc}")
            self._modem = None
        logger.info("Disconnected")
        self.disconnected.emit()

    @Slot(str)
    def send_command(self, cmd: str) -> None:
        """Send a command string (e.g. 'ping', 'beep 3')."""
        if not self._modem or not self._modem.is_connected:
            self.error.emit("Not connected.")
            return
        logger.debug(f"TX: {cmd}")
        try:
            self._modem.write(cmd)
        except Exception as exc:
            logger.error(f"Send error: {exc}")
            self.error.emit(str(exc))

    def list_ports(self) -> list[str]:
        """Return available serial port names."""
        modem = Modem()
        return modem.list_ports()

    @property
    def is_connected(self) -> bool:
        return self._modem is not None and self._modem.is_connected

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _setup_modem(self) -> None:
        if self._modem is not None:
            self.disconnect()
        self._modem = Modem()

    def _start_reader(self) -> None:
        self._reader = _ReaderThread(self._modem, parent=self)
        self._reader.message_received.connect(self._on_message)
        self._reader.start()

    @Slot()
    def _check_subprocess(self) -> None:
        """Watchdog: detect if the kitsat serial subprocess died unexpectedly."""
        if self._modem is None:
            return
        proc = getattr(self._modem, "_serial_process", None)
        if proc is not None and not proc.is_alive():
            exit_code = proc.exitcode
            logger.error(
                f"Serial subprocess died (exit code {exit_code}). "
                "Check that the COM port is not already in use by another program."
            )
            self._watchdog.stop()
            self.error.emit(
                f"Serial subprocess crashed (exit {exit_code}). "
                "Disconnect and reconnect to try again."
            )

    @Slot(object)
    def _on_message(self, msg: object) -> None:
        logger.debug(f"RX: {msg}")
        self.message_received.emit(msg)
