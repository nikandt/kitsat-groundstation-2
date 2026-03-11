"""
ImageManager — monitors the kitsat data directory for new JPEG images
and emits Qt signals when they appear.

kitsat stores images at:
  {kitsat_pkg}/data/files/{session_time}/downloaded/image-N.jpeg
  {kitsat_pkg}/data/files/{session_time}/streamed/image-N.jpeg

We watch the entire data/files/ subtree using QFileSystemWatcher,
adding new session directories as they are created.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, QFileSystemWatcher, QTimer
from loguru import logger


@dataclass
class ImageRecord:
    path: Path
    source: str      # "downloaded" or "streamed"
    session: str     # session timestamp string


def _find_kitsat_data_root() -> Optional[Path]:
    """Locate kitsat's data directory regardless of install location."""
    try:
        import kitsat
        pkg_root = Path(kitsat.__file__).parent
        data = pkg_root / "data" / "files"
        data.mkdir(parents=True, exist_ok=True)
        return data
    except ImportError:
        logger.warning("ImageManager: kitsat package not found")
        return None


class ImageManager(QObject):
    """
    Signals:
        image_received(record)  — emitted when a new complete JPEG appears
        session_started(name)   — emitted when a new session directory appears
    """

    image_received = Signal(object)    # ImageRecord
    session_started = Signal(str)      # session name

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data_root: Optional[Path] = _find_kitsat_data_root()
        self._known_files: set[Path] = set()
        self._known_sessions: set[str] = set()

        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_directory_changed)
        self._watcher.fileChanged.connect(self._on_file_changed)

        # Poll timer — QFileSystemWatcher can miss deeply nested additions
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._scan)
        self._poll_timer.start(2000)

        self._start()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _start(self) -> None:
        if self._data_root is None:
            return
        if self._data_root.exists():
            self._watcher.addPath(str(self._data_root))
        self._scan()

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def _scan(self) -> None:
        if self._data_root is None or not self._data_root.exists():
            return

        for session_dir in self._data_root.iterdir():
            if not session_dir.is_dir():
                continue
            session = session_dir.name
            if session not in self._known_sessions:
                self._known_sessions.add(session)
                self._watcher.addPath(str(session_dir))
                logger.info(f"ImageManager: new session {session}")
                self.session_started.emit(session)

            for source in ("downloaded", "streamed"):
                source_dir = session_dir / source
                if not source_dir.exists():
                    continue
                if str(source_dir) not in self._watcher.directories():
                    self._watcher.addPath(str(source_dir))
                for jpeg in source_dir.glob("*.jpeg"):
                    if jpeg not in self._known_files:
                        self._known_files.add(jpeg)
                        record = ImageRecord(path=jpeg, source=source, session=session)
                        logger.info(f"ImageManager: new image {jpeg.name} ({source})")
                        self.image_received.emit(record)

    # ------------------------------------------------------------------
    # QFileSystemWatcher callbacks
    # ------------------------------------------------------------------

    def _on_directory_changed(self, _path: str) -> None:
        self._scan()

    def _on_file_changed(self, path: str) -> None:
        # A .blocks file becoming a .jpeg triggers this
        self._scan()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def all_images(self) -> list[ImageRecord]:
        """Return all known images sorted by modification time."""
        records = []
        for p in self._known_files:
            if p.exists():
                source = p.parent.name
                session = p.parent.parent.name
                records.append(ImageRecord(path=p, source=source, session=session))
        return sorted(records, key=lambda r: r.path.stat().st_mtime)

    @property
    def data_root(self) -> Optional[Path]:
        return self._data_root
