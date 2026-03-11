"""
ImageWidget — satellite image gallery and viewer.

Layout:
  ┌─────────────────────────────────────────────┐
  │  Header + status bar                        │
  ├──────────────┬──────────────────────────────┤
  │  Thumbnail   │                              │
  │  sidebar     │   Full-size image viewer     │
  │  (scrollable)│   with zoom / fit controls   │
  │              │                              │
  └──────────────┴──────────────────────────────┘

New images are added automatically via ImageManager signals.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QPushButton, QSplitter,
    QListWidget, QListWidgetItem, QFileDialog,
    QSizePolicy, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem,
)
from PySide6.QtCore import Qt, Slot, QSize
from PySide6.QtGui import QPixmap, QTransform, QIcon
from loguru import logger

from kitsat_gs.core.image_manager import ImageManager, ImageRecord


class _ZoomableView(QGraphicsView):
    """QGraphicsView with mouse-wheel zoom and fit-to-window."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setRenderHint(self.renderHints())
        self.setBackgroundBrush(Qt.black)
        self.setObjectName("imageViewer")

    def set_image(self, path: Path) -> None:
        pix = QPixmap(str(path))
        if pix.isNull():
            logger.warning(f"Could not load image: {path}")
            return
        self._scene.clear()
        self._pixmap_item = self._scene.addPixmap(pix)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self.fit()

    def fit(self) -> None:
        if self._pixmap_item:
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit()


_THUMB_SIZE = QSize(120, 90)


class _ThumbItem(QListWidgetItem):
    def __init__(self, record: ImageRecord) -> None:
        super().__init__()
        self.record = record
        pix = QPixmap(str(record.path))
        if not pix.isNull():
            self.setIcon(QIcon(pix.scaled(_THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
        source_label = "📡 stream" if record.source == "streamed" else "⬇ download"
        self.setText(f"{record.path.name}\n{source_label}")
        self.setToolTip(str(record.path))
        self.setSizeHint(QSize(130, 110))


class ImageWidget(QWidget):
    def __init__(self, manager: ImageManager, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._manager.image_received.connect(self._on_image_received)
        self._current_record: Optional[ImageRecord] = None
        self._build_ui()
        self._load_existing()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header row
        hdr_row = QHBoxLayout()
        header = QLabel("Images")
        header.setObjectName("panelHeader")
        hdr_row.addWidget(header)
        hdr_row.addStretch()

        self._status = QLabel("No images received yet")
        self._status.setObjectName("versionLabel")
        hdr_row.addWidget(self._status)
        layout.addLayout(hdr_row)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left: thumbnail list
        self._thumb_list = QListWidget()
        self._thumb_list.setIconSize(_THUMB_SIZE)
        self._thumb_list.setViewMode(QListWidget.IconMode)
        self._thumb_list.setResizeMode(QListWidget.Adjust)
        self._thumb_list.setMovement(QListWidget.Static)
        self._thumb_list.setObjectName("thumbList")
        self._thumb_list.setMinimumWidth(148)
        self._thumb_list.setMaximumWidth(160)
        self._thumb_list.currentItemChanged.connect(self._on_thumb_selected)
        splitter.addWidget(self._thumb_list)

        # Right: viewer + toolbar
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        # Viewer toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._btn_fit = QPushButton("Fit")
        self._btn_fit.setFixedWidth(50)
        self._btn_fit.clicked.connect(self._on_fit)
        toolbar.addWidget(self._btn_fit)

        self._btn_zoom_in = QPushButton("+")
        self._btn_zoom_in.setFixedWidth(36)
        self._btn_zoom_in.clicked.connect(lambda: self._viewer.scale(1.3, 1.3))
        toolbar.addWidget(self._btn_zoom_in)

        self._btn_zoom_out = QPushButton("−")
        self._btn_zoom_out.setFixedWidth(36)
        self._btn_zoom_out.clicked.connect(lambda: self._viewer.scale(1 / 1.3, 1 / 1.3))
        toolbar.addWidget(self._btn_zoom_out)

        toolbar.addStretch()

        self._lbl_filename = QLabel("")
        self._lbl_filename.setObjectName("versionLabel")
        toolbar.addWidget(self._lbl_filename)

        toolbar.addStretch()

        self._btn_save = QPushButton("Save Copy…")
        self._btn_save.setFixedWidth(90)
        self._btn_save.setEnabled(False)
        self._btn_save.clicked.connect(self._on_save)
        toolbar.addWidget(self._btn_save)

        self._btn_open_folder = QPushButton("Open Folder")
        self._btn_open_folder.setFixedWidth(100)
        self._btn_open_folder.setEnabled(False)
        self._btn_open_folder.clicked.connect(self._on_open_folder)
        toolbar.addWidget(self._btn_open_folder)

        right_layout.addLayout(toolbar)

        self._viewer = _ZoomableView()
        right_layout.addWidget(self._viewer, stretch=1)

        splitter.addWidget(right)
        splitter.setSizes([155, 800])
        layout.addWidget(splitter, stretch=1)

    def _load_existing(self) -> None:
        for record in self._manager.all_images():
            self._add_thumbnail(record)
        self._update_status()

    @Slot(object)
    def _on_image_received(self, record: ImageRecord) -> None:
        self._add_thumbnail(record)
        self._update_status()
        # Auto-select newest if nothing is selected
        if self._thumb_list.currentItem() is None:
            self._thumb_list.setCurrentRow(self._thumb_list.count() - 1)

    def _add_thumbnail(self, record: ImageRecord) -> None:
        item = _ThumbItem(record)
        self._thumb_list.addItem(item)

    def _update_status(self) -> None:
        n = self._thumb_list.count()
        self._status.setText(f"{n} image{'s' if n != 1 else ''} received")

    @Slot()
    def _on_thumb_selected(self, current: QListWidgetItem, _prev) -> None:
        if not isinstance(current, _ThumbItem):
            return
        self._current_record = current.record
        self._viewer.set_image(current.record.path)
        self._lbl_filename.setText(current.record.path.name)
        self._btn_save.setEnabled(True)
        self._btn_open_folder.setEnabled(True)

    @Slot()
    def _on_fit(self) -> None:
        self._viewer.fit()

    @Slot()
    def _on_save(self) -> None:
        if self._current_record is None:
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save Image", self._current_record.path.name,
            "JPEG images (*.jpeg *.jpg)"
        )
        if dest:
            shutil.copy2(self._current_record.path, dest)
            logger.info(f"Image saved to {dest}")

    @Slot()
    def _on_open_folder(self) -> None:
        if self._current_record is None:
            return
        import subprocess, sys
        folder = str(self._current_record.path.parent)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", folder])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
